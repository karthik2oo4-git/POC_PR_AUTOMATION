from __future__ import annotations

import json

from fastapi import APIRouter, Header, HTTPException, Request, status

from github_ci_governance_app.core.logging import get_logger
from github_ci_governance_app.core.settings import get_settings
from github_ci_governance_app.domain.governance_models import (
    PullRequestContext,
    PushContext,
    RepositoryContext,
    ValidationStatus,
    WorkflowRunContext,
)
from github_ci_governance_app.integrations.github.client import GitHubClient
from github_ci_governance_app.services.checks import InMemoryCheckPublisher
from github_ci_governance_app.services.comments import InMemoryPullRequestCommentService
from github_ci_governance_app.services.delivery_store import InMemoryDeliveryStore
from github_ci_governance_app.services.governance import GovernanceService
from github_ci_governance_app.services.signature import SignatureValidationError, validate_github_signature
from github_ci_governance_app.services.validation_state import InMemoryValidationStateStore

router = APIRouter()
logger = get_logger(__name__)
delivery_store = InMemoryDeliveryStore()
validation_state = InMemoryValidationStateStore()
check_publisher = InMemoryCheckPublisher()
comment_service = InMemoryPullRequestCommentService()


def _build_governance_service() -> GovernanceService:
    settings = get_settings()
    github_client = GitHubClient(settings)
    return GovernanceService(
        settings=settings,
        github_client=github_client,
        validation_state=validation_state,
        checks=check_publisher,
        comments=comment_service,
    )


def _repository_from_payload(payload: dict[str, object]) -> RepositoryContext:
    repository = payload["repository"]
    if not isinstance(repository, dict):
        raise ValueError("Invalid repository payload")
    owner = repository["owner"]
    if not isinstance(owner, dict):
        raise ValueError("Invalid repository owner payload")
    login = owner["login"]
    name = repository["name"]
    if not isinstance(login, str) or not isinstance(name, str):
        raise ValueError("Invalid repository identity")
    return RepositoryContext(owner=login, name=name)


def _installation_id_from_payload(payload: dict[str, object]) -> int:
    installation = payload["installation"]
    if not isinstance(installation, dict):
        raise ValueError("Invalid installation payload")
    installation_id = installation["id"]
    if not isinstance(installation_id, int):
        raise ValueError("Invalid installation id")
    return installation_id


def _normalize_branch(ref: str) -> str:
    return ref.removeprefix("refs/heads/")


def _workflow_status_from_conclusion(conclusion: str | None) -> ValidationStatus:
    mapping = {
        None: ValidationStatus.IN_PROGRESS,
        "success": ValidationStatus.SUCCESS,
        "failure": ValidationStatus.FAILURE,
        "cancelled": ValidationStatus.CANCELLED,
        "timed_out": ValidationStatus.TIMED_OUT,
        "action_required": ValidationStatus.FAILURE,
        "neutral": ValidationStatus.SUCCESS,
    }
    return mapping.get(conclusion, ValidationStatus.FAILURE)


@router.post("/github", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(
    request: Request,
    x_github_event: str = Header(alias="X-GitHub-Event"),
    x_github_delivery: str = Header(alias="X-GitHub-Delivery"),
    x_hub_signature_256: str | None = Header(default=None, alias="X-Hub-Signature-256"),
) -> dict[str, str]:
    settings = get_settings()
    payload = await request.body()

    try:
        validate_github_signature(settings.github_webhook_secret, payload, x_hub_signature_256)
    except SignatureValidationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    if x_github_event not in settings.allowed_events:
        logger.info("event_ignored event=%s delivery_id=%s", x_github_event, x_github_delivery)
        return {"status": "ignored", "event": x_github_event}

    if delivery_store.seen(x_github_delivery):
        logger.info("duplicate_delivery_ignored delivery_id=%s event=%s", x_github_delivery, x_github_event)
        return {"status": "duplicate_ignored"}

    delivery_store.mark(x_github_delivery, x_github_event)

    try:
        event_payload = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed JSON payload") from exc

    if not isinstance(event_payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed webhook payload")

    governance_service = _build_governance_service()

    try:
        if x_github_event == "push":
            repository = _repository_from_payload(event_payload)
            ref = event_payload.get("ref")
            after = event_payload.get("after")
            if not isinstance(ref, str) or not isinstance(after, str):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed push payload")
            result = await governance_service.handle_push(
                PushContext(
                    repository=repository,
                    branch=_normalize_branch(ref),
                    sha=after,
                    installation_id=_installation_id_from_payload(event_payload),
                    delivery_id=x_github_delivery,
                )
            )
            return result

        if x_github_event == "pull_request":
            action = event_payload.get("action")
            if action not in {"opened", "synchronize", "reopened"}:
                logger.info("pull_request_action_ignored action=%s delivery_id=%s", action, x_github_delivery)
                return {"status": "ignored", "event": x_github_event}
            repository = _repository_from_payload(event_payload)
            pull_request = event_payload.get("pull_request")
            if not isinstance(pull_request, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed pull_request payload")
            number = event_payload.get("number")
            head = pull_request.get("head")
            base = pull_request.get("base")
            if not isinstance(number, int) or not isinstance(head, dict) or not isinstance(base, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed pull_request payload")
            head_ref = head.get("ref")
            head_sha = head.get("sha")
            base_ref = base.get("ref")
            if not isinstance(head_ref, str) or not isinstance(head_sha, str) or not isinstance(base_ref, str):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed pull_request refs")
            result = await governance_service.handle_pull_request(
                PullRequestContext(
                    repository=repository,
                    number=number,
                    branch=head_ref,
                    base_branch=base_ref,
                    sha=head_sha,
                    installation_id=_installation_id_from_payload(event_payload),
                    delivery_id=x_github_delivery,
                )
            )
            return result

        if x_github_event == "workflow_run":
            workflow_run = event_payload.get("workflow_run")
            repository = _repository_from_payload(event_payload)
            if not isinstance(workflow_run, dict):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed workflow_run payload")
            head_branch = workflow_run.get("head_branch")
            head_sha = workflow_run.get("head_sha")
            name = workflow_run.get("name")
            run_id = workflow_run.get("id")
            html_url = workflow_run.get("html_url")
            conclusion = workflow_run.get("conclusion")
            if (
                not isinstance(head_branch, str)
                or not isinstance(head_sha, str)
                or not isinstance(name, str)
                or not isinstance(run_id, int)
                or (html_url is not None and not isinstance(html_url, str))
                or (conclusion is not None and not isinstance(conclusion, str))
            ):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed workflow_run payload")
            result = await governance_service.handle_workflow_run(
                WorkflowRunContext(
                    repository=repository,
                    branch=head_branch,
                    sha=head_sha,
                    workflow_name=name,
                    workflow_run_id=run_id,
                    conclusion=_workflow_status_from_conclusion(conclusion),
                    details_url=html_url,
                    installation_id=_installation_id_from_payload(event_payload),
                    delivery_id=x_github_delivery,
                )
            )
            return result
    except HTTPException:
        raise
    except ValueError as exc:
        logger.error(
            "webhook_processing_configuration_error repository=%s event=%s delivery_id=%s error=%s",
            event_payload.get("repository", {}).get("full_name", "unknown") if isinstance(event_payload.get("repository"), dict) else "unknown",
            x_github_event,
            x_github_delivery,
            str(exc),
        )
        return {"status": "ignored", "reason": "configuration_error"}

    logger.info("webhook_accepted delivery_id=%s event=%s", x_github_delivery, x_github_event)
    return {"status": "accepted"}

# Made with Bob
