import allure
import pytest

from framework import endpoint
from framework.data import random_uuid, unique_name
from services.layout_manager.models import LEGACY_WIDGET_FIELDS, AccessRole, WidgetItem, WidgetsPage
from tests.fixtures.factories import default_widget_payload

SERVICE = "layout-manager"
WIDGETS = "/public/v4/widgets"
WIDGET = "/public/v4/widgets/{widget_id}"
COPY = "/public/v4/widgets/{widget_id}/copy"
LIST = "/public/v4/widgets/list"

# Настройки виджета, которые фронт хранит в state (период, фильтры)
WIDGET_SETTINGS = {"period": "1d", "detalization": 3600, "filters": {"gender": [1], "age": [18, 65]}}

# Legacy-поля, которые старые клиенты могут ещё присылать. После MR они должны игнорироваться.
LEGACY_PAYLOADS = [
    pytest.param({"online": True, "filters": {"a": 1}, "detalization": 60, "timeslice": random_uuid()}, id="valid_legacy"),
    pytest.param({"filters": ["face"], "timeslice": None, "detalization": 86400}, id="list_filters"),
    # до MR: несуществующий timeslice -> 404, невалидный -> 422. Теперь поле игнорируется.
    pytest.param({"timeslice": "not-a-uuid", "detalization": "abc", "online": "yes"}, id="invalid_types"),
]


def assert_no_legacy_fields(item: dict) -> None:
    leaked = LEGACY_WIDGET_FIELDS & set(item)
    assert not leaked, f"в ответе остались legacy-поля {sorted(leaked)}: {item}"


@allure.feature("layout-manager")
@allure.story("widgets")
class TestWidgets:
    @pytest.mark.smoke
    @endpoint(SERVICE, "POST", WIDGETS)
    @endpoint(SERVICE, "GET", WIDGET)
    def test_create_and_get(self, layout_api, widget_factory, me):
        w = widget_factory(state=WIDGET_SETTINGS)
        resp = layout_api.get_widget(w["id"]).assert_status(200).assert_contract()
        assert_no_legacy_fields(resp.json())
        item = resp.parse(WidgetItem)
        assert item.name == w["payload"]["name"]
        assert item.type == w["payload"]["type"]
        assert item.state == WIDGET_SETTINGS
        assert item.user_id == me["id"]
        assert item.access_role is AccessRole.OWNER
        assert item.is_shared is False
        assert item.parent_layout_id is None

    @endpoint(SERVICE, "POST", WIDGETS)
    def test_create_minimal(self, layout_api, cleanup):
        created = layout_api.create_widget({"type": "numeric", "name": unique_name("widget")}).assert_status(201).assert_contract().json()
        cleanup.add("widget", lambda: layout_api.delete_widget(created["id"]))
        item = layout_api.get_widget(created["id"]).assert_status(200).json()
        assert item["state"] == {}
        assert_no_legacy_fields(item)

    @pytest.mark.parametrize("legacy", LEGACY_PAYLOADS)
    @endpoint(SERVICE, "POST", WIDGETS)
    def test_create_legacy_fields_ignored(self, layout_api, cleanup, legacy):
        payload = default_widget_payload(state={"period": "1w"}, **legacy)
        created = layout_api.create_widget(payload).assert_status(201).assert_contract().json()
        cleanup.add("widget", lambda: layout_api.delete_widget(created["id"]))
        item = layout_api.get_widget(created["id"]).assert_status(200).json()
        assert_no_legacy_fields(item)
        assert item["state"] == {"period": "1w"}, "state не должен смешиваться с legacy-полями"

    @pytest.mark.parametrize("missing", ["type", "name"])
    @endpoint(SERVICE, "POST", WIDGETS)
    def test_create_missing_required(self, layout_api, missing):
        payload = default_widget_payload()
        payload.pop(missing)
        layout_api.create_widget(payload).assert_validation_error(missing)

    @endpoint(SERVICE, "POST", WIDGETS)
    def test_create_unauthorized(self, anon_layout, bad_token):
        anon_layout.with_token(bad_token).create_widget(default_widget_payload()).assert_unauthorized()

    @endpoint(SERVICE, "GET", WIDGET)
    def test_get_not_found(self, layout_api):
        layout_api.get_widget(random_uuid()).assert_error(404)

    @endpoint(SERVICE, "PATCH", WIDGET)
    def test_rename(self, layout_api, widget_factory):
        w = widget_factory(state=WIDGET_SETTINGS)
        new_name = unique_name("widget_renamed")
        layout_api.edit_widget(w["id"], {"name": new_name}).assert_status(200).assert_contract()
        item = layout_api.get_widget(w["id"]).json()
        assert item["name"] == new_name
        assert item["type"] == w["payload"]["type"], "неизменённые поля должны сохраниться"
        assert item["state"] == WIDGET_SETTINGS

    @endpoint(SERVICE, "PATCH", WIDGET)
    def test_change_settings_persisted(self, layout_api, widget_factory):
        """Смена периода и фильтров (state) сохраняется — эквивалент «перезагрузки страницы» на фронте."""
        w = widget_factory(state=WIDGET_SETTINGS)
        new_state = {"period": "1w", "detalization": 86400, "filters": {"gender": [0]}}
        layout_api.edit_widget(w["id"], {"state": new_state, "type": "hist_chart"}).assert_status(200).assert_contract()
        item = layout_api.get_widget(w["id"]).json()
        assert item["state"] == new_state
        assert item["type"] == "hist_chart"
        assert item["name"] == w["payload"]["name"]

    @pytest.mark.parametrize("legacy", LEGACY_PAYLOADS)
    @endpoint(SERVICE, "PATCH", WIDGET)
    def test_edit_legacy_only_is_noop(self, layout_api, widget_factory, legacy):
        w = widget_factory(state=WIDGET_SETTINGS)
        before = layout_api.get_widget(w["id"]).json()
        layout_api.edit_widget(w["id"], legacy).assert_status(200).assert_contract()
        after = layout_api.get_widget(w["id"]).json()
        assert after == before, "PATCH только legacy-полями не должен ничего менять"

    @endpoint(SERVICE, "PATCH", WIDGET)
    def test_edit_not_found(self, layout_api):
        layout_api.edit_widget(random_uuid(), {"name": unique_name("x")}).assert_error(404)

    @endpoint(SERVICE, "DELETE", WIDGET)
    def test_delete(self, layout_api):
        created = layout_api.create_widget(default_widget_payload()).assert_status(201).json()
        layout_api.delete_widget(created["id"]).assert_status(204)
        layout_api.get_widget(created["id"]).assert_status(404)

    @endpoint(SERVICE, "DELETE", WIDGET)
    def test_delete_not_found(self, layout_api):
        layout_api.delete_widget(random_uuid()).assert_error(404)

    @endpoint(SERVICE, "POST", COPY)
    def test_copy(self, layout_api, widget_factory, cleanup):
        src = widget_factory(state=WIDGET_SETTINGS)
        copy_name = unique_name("widget_copy")
        copied = layout_api.copy_widget(src["id"], {"name": copy_name}).assert_status(201).assert_contract().json()
        cleanup.add("widget copy", lambda: layout_api.delete_widget(copied["id"]))
        assert copied["id"] != src["id"]
        item = layout_api.get_widget(copied["id"]).json()
        assert item["name"] == copy_name
        assert item["type"] == src["payload"]["type"]
        assert item["state"] == WIDGET_SETTINGS, "настройки наследуются от исходного виджета"
        assert item["access_role"] == "owner" and item["is_shared"] is False
        assert layout_api.get_widget(src["id"]).json()["name"] == src["payload"]["name"], "исходный виджет не изменился"

    @endpoint(SERVICE, "POST", COPY)
    def test_copy_with_overrides_and_legacy(self, layout_api, widget_factory, cleanup):
        src = widget_factory(state=WIDGET_SETTINGS)
        body = {"name": unique_name("widget_copy"), "type": "line_chart", "state": {"period": "2w"}, "online": True, "timeslice": random_uuid()}
        copied = layout_api.copy_widget(src["id"], body).assert_status(201).json()
        cleanup.add("widget copy", lambda: layout_api.delete_widget(copied["id"]))
        item = layout_api.get_widget(copied["id"]).json()
        assert (item["type"], item["state"]) == ("line_chart", {"period": "2w"})
        assert_no_legacy_fields(item)

    @endpoint(SERVICE, "POST", COPY)
    def test_copy_not_found(self, layout_api):
        layout_api.copy_widget(random_uuid(), {"name": unique_name("x")}).assert_error(404)

    @endpoint(SERVICE, "POST", LIST)
    def test_list_my(self, layout_api, widget_factory):
        w = widget_factory()
        resp = layout_api.list_widgets(pgsize=100, scope="my").assert_status(200).assert_contract()
        for raw in resp.json()["items"]:
            assert_no_legacy_fields(raw)
        page = resp.parse(WidgetsPage)
        assert w["id"] in {i.id for i in page.items}
        assert all(i.access_role is AccessRole.OWNER for i in page.items)

    @endpoint(SERVICE, "POST", LIST)
    def test_list_embedded_filter(self, layout_api, widget_factory, layout_factory):
        from tests.fixtures.factories import grid_item

        standalone, embedded = widget_factory(), widget_factory()
        layout_factory(grid=[grid_item(embedded["id"])])
        not_embedded = {i["id"] for i in layout_api.list_widgets(pgsize=100, scope="my", embedded=False).assert_status(200).json()["items"]}
        only_embedded = {i["id"] for i in layout_api.list_widgets(pgsize=100, scope="my", embedded=True).assert_status(200).json()["items"]}
        assert standalone["id"] in not_embedded and embedded["id"] not in not_embedded
        assert embedded["id"] in only_embedded and standalone["id"] not in only_embedded

    @endpoint(SERVICE, "POST", LIST)
    def test_list_pagination(self, layout_api, widget_factory):
        for _ in range(2):
            widget_factory()
        page = layout_api.list_widgets(pgoffset=0, pgsize=1).assert_status(200).json()
        assert len(page["items"]) == 1
        assert page["pagination"]["amount"] >= 2

    @endpoint(SERVICE, "POST", LIST)
    def test_list_invalid_scope(self, layout_api):
        layout_api.list_widgets(scope="everything").assert_validation_error("scope")
