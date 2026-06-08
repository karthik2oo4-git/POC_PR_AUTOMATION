from __future__ import annotations

import hashlib
import hmac


class SignatureValidationError(ValueError):
    pass


def validate_github_signature(secret: str, payload: bytes, signature_header: str | None) -> None:
    if not signature_header:
        raise SignatureValidationError("Missing X-Hub-Signature-256 header")

    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header):
        raise SignatureValidationError("Invalid GitHub webhook signature")

# Made with Bob
