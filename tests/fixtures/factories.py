"""Фабрики тестовых сущностей. Каждая фабрика:
  * создаёт сущность через API (с префиксом autotest_ в имени);
  * регистрирует удаление в `cleanup`;
  * возвращает тело ответа (dict).

Использование:
    def test_x(location_factory):
        loc = location_factory(description="...")
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from framework.data import unique_name
from services.object_manager.models import WatchlistType


@pytest.fixture
def location_factory(devices_api, cleanup) -> Callable[..., dict]:
    def create(**overrides) -> dict:
        payload = {"name": unique_name("location"), **overrides}
        body = devices_api.create_location(payload).assert_status(200).json()
        cleanup.add(f"location {body['id']}", lambda: devices_api.delete_location(body["id"]))
        return body

    return create


@pytest.fixture
def watchlist_factory(watchlists_api, cleanup) -> Callable[..., dict]:
    def create(object_type: str = WatchlistType.FACE.value, name: str | None = None) -> dict:
        body = watchlists_api.create_watchlist(name or unique_name("watchlist"), object_type).assert_status(201).json()
        cleanup.add(f"watchlist {body['id']}", lambda: watchlists_api.delete_watchlist(body["id"]))
        return body

    return create


# Формат взят из unit-тестов object-manager (tests/unit/api/watchlist_manager/test_create_predicate.py)
DEFAULT_FACE_PREDICATE = {"person_age": [18, 65], "name": "autotest"}


@pytest.fixture
def predicate_factory(watchlists_api, watchlist_factory, cleanup) -> Callable[..., dict]:
    def create(watchlist_id: int | None = None, filter_: dict | None = None) -> dict:
        wl_id = watchlist_id or watchlist_factory()["id"]
        body = watchlists_api.create_predicate(wl_id, filter_ or DEFAULT_FACE_PREDICATE).assert_status(201).json()
        cleanup.add(f"predicate {body['id']}", lambda: watchlists_api.delete_predicate(body["id"]))
        return body

    return create


def default_widget_payload(**overrides) -> dict:
    # Настройки виджета (период, фильтры) живут в state.
    # online/filters/timeslice/detalization — legacy: API их игнорирует и не возвращает.
    return {
        "type": "pie_chart",
        "name": unique_name("widget"),
        "state": {},
        **overrides,
    }


@pytest.fixture
def widget_factory(layout_api, cleanup) -> Callable[..., dict]:
    """Возвращает {'id': ..., 'payload': {...}}."""

    def create(**overrides) -> dict:
        payload = default_widget_payload(**overrides)
        created = layout_api.create_widget(payload).assert_status(201).json()
        cleanup.add(f"widget {created['id']}", lambda: layout_api.delete_widget(created["id"]))
        return {"id": created["id"], "payload": payload}

    return create


def grid_item(widget_id: str, x: int = 0, y: int = 0, w: int = 4, h: int = 4) -> dict:
    return {"id": widget_id, "x": x, "y": y, "w": w, "h": h}


@pytest.fixture
def layout_factory(layout_api, cleanup) -> Callable[..., dict]:
    def create(**overrides) -> dict:
        payload = {"name": unique_name("layout"), "grid": [], "ordering": 0, "state": {}, **overrides}
        created = layout_api.create_layout(payload).assert_status(201).json()
        cleanup.add(f"layout {created['id']}", lambda: layout_api.delete_layout(created["id"]))
        return {"id": created["id"], "payload": payload}

    return create


@pytest.fixture
def user_state_keys(auth_api, cleanup) -> Callable[..., list[str]]:
    """Генерирует уникальные ключи user state и удаляет их после теста."""

    def make(n: int = 1) -> list[str]:
        keys = [unique_name("state_key") for _ in range(n)]
        cleanup.add(f"user state {keys}", lambda: auth_api.delete_user_state(keys))
        return keys

    return make


@pytest.fixture
def company_state_keys(auth_api, cleanup) -> Callable[..., list[str]]:
    def make(n: int = 1) -> list[str]:
        keys = [unique_name("state_key") for _ in range(n)]
        cleanup.add(f"company state {keys}", lambda: auth_api.delete_company_state(keys))
        return keys

    return make


def _known_objects(om_api, limit: int = 20) -> list[dict]:
    """Объекты компании, найденные НЕ через поиск: names -> GET по id. Нужны, чтобы баг в поиске
    не превращал объектные тесты в skip и чтобы проверять сам поиск на известных данных."""
    found = []
    for object_type in ("face", "vehicle", "person"):
        names = om_api.names(object_type, limit=limit)
        if names.status_code != 200:
            continue
        for item in names.json():
            obj = om_api.get_object(item["id"])
            if obj.status_code == 200:
                body = obj.json()
                body["camera_id"] = body.get("camera")
                found.append(body)
                break
    return found


@pytest.fixture(scope="session")
def any_object(om_api) -> dict:
    """Любой существующий объект компании: сначала через v3 search, иначе через names -> GET по id."""
    for object_type in ("face", "vehicle", "person"):
        resp = om_api.search(object_type, {"pagination": {"pgoffset": 0, "pgsize": 1}})
        if resp.status_code == 200 and resp.json()["items"]:
            return resp.json()["items"][0]
    known = _known_objects(om_api)
    if known:
        return known[0]
    pytest.skip("В компании тестового пользователя нет объектов")


@pytest.fixture(scope="session")
def known_object(om_api) -> dict:
    """Объект, найденный в обход поиска (для проверки самого поиска)."""
    known = _known_objects(om_api)
    if not known:
        pytest.skip("Нет именованных объектов (names) — не на чем проверить поиск")
    return known[0]


@pytest.fixture(scope="session")
def any_camera(devices_api) -> dict:
    cameras = devices_api.cameras().assert_status(200).json()
    if not cameras:
        pytest.skip("В компании тестового пользователя нет камер")
    return cameras[0]
