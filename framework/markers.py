"""Маркер связи теста с эндпоинтом спеки.

    @endpoint("layout-manager", "POST", "/public/v4/widgets")
    def test_create_widget(...): ...

Используется:
  * tools.coverage — какие эндпоинты спеки покрыты тестами;
  * агентом анализа MR — какие тесты запускать/дописывать;
  * conftest — авто-skip, если эндпоинт не опубликован при текущем API_ROUTING;
  * Allure — группировка по сервису/эндпоинту.
"""

from __future__ import annotations

import pytest

from framework.routing import SERVICES


def endpoint(service: str, method: str, path: str):
    if service not in SERVICES:
        raise ValueError(f"Неизвестный сервис {service!r}; доступны {sorted(SERVICES)}")
    return pytest.mark.api(service=service, method=method.upper(), path=path)


def endpoint_of(item: pytest.Item) -> list[tuple[str, str, str]]:
    return [(m.kwargs["service"], m.kwargs["method"], m.kwargs["path"]) for m in item.iter_markers("api")]
