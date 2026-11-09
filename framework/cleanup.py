"""Реестр teardown-действий: всё, что тест создал, удаляется в обратном порядке,
даже если тест упал. Ошибки удаления логируются, но не роняют прогон."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

log = logging.getLogger("api.cleanup")


class Cleanup:
    def __init__(self) -> None:
        self._actions: list[tuple[str, Callable[[], Any]]] = []

    def add(self, description: str, action: Callable[[], Any]) -> None:
        self._actions.append((description, action))

    def run(self) -> None:
        while self._actions:
            description, action = self._actions.pop()
            try:
                result = action()
                status = getattr(result, "status_code", None)
                if status is not None and status >= 400 and status != 404:
                    log.warning("cleanup %s: HTTP %s", description, status)
            except Exception as exc:  # noqa: BLE001
                log.warning("cleanup %s failed: %s", description, exc)
