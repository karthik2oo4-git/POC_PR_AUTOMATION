from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt
from jwt import InvalidKeyError

from github_ci_governance_app.core.settings import Settings


def _load_private_key(settings: Settings) -> str:
    if settings.github_private_key_path:
        return Path(settings.github_private_key_path).read_text(encoding="utf-8").strip()
    if settings.github_private_key:
        return settings.github_private_key.replace("\\n", "\n").strip()
    raise ValueError("Missing GitHub App private key. Set GITHUB_PRIVATE_KEY_PATH or GITHUB_PRIVATE_KEY.")


def build_app_jwt(settings: Settings) -> str:
    now = datetime.now(UTC)
    payload = {
        "iat": int((now - timedelta(seconds=60)).timestamp()),
        "exp": int((now + timedelta(minutes=9)).timestamp()),
        "iss": str(settings.github_app_id),
    }
    private_key = _load_private_key(settings)
    try:
        return jwt.encode(payload, private_key, algorithm="RS256")
    except InvalidKeyError as exc:
        raise ValueError(
            "Invalid GitHub App private key format. Prefer GITHUB_PRIVATE_KEY_PATH for local development, "
            "or provide valid PEM content in GITHUB_PRIVATE_KEY."
        ) from exc

# Made with Bob
