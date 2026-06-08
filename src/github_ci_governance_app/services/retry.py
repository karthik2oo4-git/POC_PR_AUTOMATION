from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from github_ci_governance_app.domain.governance_models import RetryPolicy

T = TypeVar("T")


async def with_retry(
    operation: Callable[[], Awaitable[T]],
    policy: RetryPolicy,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    attempt = 0
    delay = policy.base_delay_seconds

    while True:
        try:
            return await operation()
        except retryable_exceptions:
            attempt += 1
            if attempt >= policy.max_attempts:
                raise
            await asyncio.sleep(min(delay, policy.max_delay_seconds))
            delay *= 2

# Made with Bob
