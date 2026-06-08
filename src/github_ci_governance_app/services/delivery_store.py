from __future__ import annotations

from collections.abc import MutableMapping


class InMemoryDeliveryStore:
    def __init__(self) -> None:
        self._deliveries: MutableMapping[str, str] = {}

    def seen(self, delivery_id: str) -> bool:
        return delivery_id in self._deliveries

    def mark(self, delivery_id: str, event_name: str) -> None:
        self._deliveries[delivery_id] = event_name

# Made with Bob
