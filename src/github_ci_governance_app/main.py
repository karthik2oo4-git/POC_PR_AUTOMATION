from fastapi import FastAPI

from github_ci_governance_app.api.webhooks import router as webhook_router
from github_ci_governance_app.core.logging import configure_logging
from github_ci_governance_app.core.settings import get_settings

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title="GitHub CI Governance App",
    version="0.1.0",
)
app.include_router(webhook_router, prefix="/webhooks")


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}

# Made with Bob
