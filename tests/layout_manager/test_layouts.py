import allure
import pytest

from framework import endpoint
from framework.data import random_uuid, unique_name
from services.layout_manager.models import LEGACY_WIDGET_FIELDS, AccessRole, LayoutItem, LayoutsPage, WidgetItem
from tests.fixtures.factories import grid_item

SERVICE = "layout-manager"
LAYOUTS = "/public/v4/layouts"
LAYOUT = "/public/v4/layouts/{layout_id}"


@allure.feature("layout-manager")
@allure.story("layouts")
class TestLayouts:
    @pytest.mark.smoke
    @endpoint(SERVICE, "POST", LAYOUTS)
    @endpoint(SERVICE, "GET", LAYOUT)
    def test_create_with_grid(self, layout_api, layout_factory, widget_factory):
        w = widget_factory()
        layout = layout_factory(grid=[grid_item(w["id"], w=6, h=3)])
        item = layout_api.get_layout(layout["id"]).assert_status(200).assert_contract().parse(LayoutItem)
        assert item.name == layout["payload"]["name"]
        assert [(g.id, g.w, g.h) for g in item.grid] == [(w["id"], 6, 3)]
        assert item.access_role is AccessRole.OWNER

    @endpoint(SERVICE, "POST", LAYOUTS)
    def test_create_without_name(self, layout_api):
        layout_api.create_layout({"grid": []}).assert_validation_error("name")

    @endpoint(SERVICE, "POST", LAYOUTS)
    def test_create_invalid_grid(self, layout_api):
        layout_api.create_layout({"name": unique_name("layout"), "grid": [{"id": random_uuid(), "x": 0}]}).assert_status(422)

    @endpoint(SERVICE, "POST", LAYOUTS)
    def test_create_unauthorized(self, anon_layout, bad_token):
        anon_layout.with_token(bad_token).create_layout({"name": unique_name("layout")}).assert_unauthorized()

    @endpoint(SERVICE, "GET", LAYOUT)
    def test_get_not_found(self, layout_api):
        layout_api.get_layout(random_uuid()).assert_error(404)

    @endpoint(SERVICE, "PATCH", LAYOUT)
    def test_modify(self, layout_api, layout_factory):
        layout = layout_factory()
        new_name = unique_name("layout_renamed")
        layout_api.modify_layout(layout["id"], {"name": new_name, "state": {"a": 1}}).assert_status(200).assert_contract()
        item = layout_api.get_layout(layout["id"]).json()
        assert item["name"] == new_name
        assert item["state"] == {"a": 1}

    @endpoint(SERVICE, "PATCH", LAYOUT)
    def test_modify_not_found(self, layout_api):
        layout_api.modify_layout(random_uuid(), {"name": "x"}).assert_error(404)

    @endpoint(SERVICE, "PATCH", LAYOUTS)
    def test_batch_modify_ordering(self, layout_api, layout_factory):
        a, b = layout_factory(), layout_factory()
        layout_api.modify_layouts([{"id": a["id"], "ordering": 5}, {"id": b["id"], "ordering": 6}]).assert_status(200).assert_contract()
        assert layout_api.get_layout(a["id"]).json()["ordering"] == 5
        assert layout_api.get_layout(b["id"]).json()["ordering"] == 6

    @endpoint(SERVICE, "PATCH", LAYOUTS)
    def test_batch_modify_without_id(self, layout_api):
        layout_api.modify_layouts([{"name": "x"}]).assert_status(422)

    @endpoint(SERVICE, "DELETE", LAYOUT)
    def test_delete(self, layout_api):
        created = layout_api.create_layout({"name": unique_name("layout")}).assert_status(201).json()
        layout_api.delete_layout(created["id"]).assert_status(204)
        layout_api.get_layout(created["id"]).assert_status(404)

    @endpoint(SERVICE, "PATCH", LAYOUT)
    def test_rearrange_and_resize(self, layout_api, layout_factory, widget_factory):
        w1, w2 = widget_factory(), widget_factory()
        layout = layout_factory(grid=[grid_item(w1["id"], x=0, y=0, w=4, h=4), grid_item(w2["id"], x=4, y=0, w=4, h=4)])
        new_grid = [grid_item(w1["id"], x=4, y=4, w=8, h=5), grid_item(w2["id"], x=0, y=0, w=2, h=3)]
        layout_api.modify_layout(layout["id"], {"grid": new_grid}).assert_status(200)
        grid = {c["id"]: (c["x"], c["y"], c["w"], c["h"]) for c in layout_api.get_layout(layout["id"]).json()["grid"]}
        assert grid == {w1["id"]: (4, 4, 8, 5), w2["id"]: (0, 0, 2, 3)}

    @endpoint(SERVICE, "PATCH", LAYOUT)
    def test_add_and_remove_widget(self, layout_api, layout_factory, widget_factory):
        keep, removed, added = widget_factory(), widget_factory(), widget_factory()
        layout = layout_factory(grid=[grid_item(keep["id"]), grid_item(removed["id"], x=4)])
        layout_api.modify_layout(layout["id"], {"grid": [grid_item(keep["id"]), grid_item(added["id"], x=4, y=4)]}).assert_status(200)

        ids = {w["id"] for w in layout_api.layout_widgets(layout["id"]).json()}
        assert ids == {keep["id"], added["id"]}
        assert layout_api.get_widget(added["id"]).json()["parent_layout_id"] == layout["id"]
        # убранный из сетки виджет не удаляется, а становится самостоятельным
        detached = layout_api.get_widget(removed["id"]).assert_status(200).json()
        assert detached["parent_layout_id"] is None

    @endpoint(SERVICE, "POST", LAYOUTS)
    def test_widget_cannot_be_in_two_layouts(self, layout_api, layout_factory, widget_factory):
        w = widget_factory()
        layout_factory(grid=[grid_item(w["id"])])
        resp = layout_api.create_layout({"name": unique_name("layout"), "grid": [grid_item(w["id"])]})
        resp.assert_error(409, message_contains="already belongs to another layout")

    @endpoint(SERVICE, "DELETE", LAYOUT)
    def test_delete_cascades_grid_widgets(self, layout_api, widget_factory):
        # Наблюдаемое поведение: удаление лейаута удаляет виджеты из его grid
        w = widget_factory()
        created = layout_api.create_layout({"name": unique_name("layout"), "grid": [grid_item(w["id"])]}).assert_status(201).json()
        layout_api.delete_layout(created["id"]).assert_status(204)
        layout_api.get_widget(w["id"]).assert_status(404)

    @endpoint(SERVICE, "DELETE", LAYOUT)
    def test_delete_not_found(self, layout_api):
        layout_api.delete_layout(random_uuid()).assert_error(404)

    @endpoint(SERVICE, "GET", "/public/v4/layouts/{layout_id}/widgets")
    def test_layout_widgets(self, layout_api, layout_factory, widget_factory):
        w1, w2 = widget_factory(), widget_factory()
        layout = layout_factory(grid=[grid_item(w1["id"]), grid_item(w2["id"], x=4)])
        resp = layout_api.layout_widgets(layout["id"]).assert_status(200).assert_contract()
        for raw in resp.json():
            assert not LEGACY_WIDGET_FIELDS & set(raw), f"legacy-поля в ответе: {raw}"
        widgets = resp.parse(list[WidgetItem])
        assert {w.id for w in widgets} == {w1["id"], w2["id"]}
        assert all(w.parent_layout_id == layout["id"] for w in widgets)

    @endpoint(SERVICE, "GET", "/public/v4/layouts/{layout_id}/widgets")
    def test_layout_widgets_not_found(self, layout_api):
        layout_api.layout_widgets(random_uuid()).assert_error(404)

    @endpoint(SERVICE, "POST", "/public/v4/layouts/{layout_id}/copy")
    def test_copy(self, layout_api, layout_factory, cleanup):
        src = layout_factory(state={"x": 1})
        name = unique_name("layout_copy")
        copied = layout_api.copy_layout(src["id"], {"name": name}).assert_status(201).assert_contract().json()
        cleanup.add("layout copy", lambda: layout_api.delete_layout(copied["id"]))
        item = layout_api.get_layout(copied["id"]).json()
        assert item["name"] == name
        assert copied["id"] != src["id"]
        assert item["grid"] == []

    @pytest.mark.smoke
    @endpoint(SERVICE, "POST", "/public/v4/layouts/{layout_id}/copy")
    def test_copy_with_widgets(self, layout_api, layout_factory, widget_factory, cleanup):
        """Виджеты копируются вместе с лейаутом: новые id, те же name/type/state и геометрия; исходник не меняется."""
        w1 = widget_factory(type="pie_chart", state={"period": "1d", "filters": {"gender": [1]}})
        w2 = widget_factory(type="line_chart", state={"period": "1w"})
        src = layout_factory(grid=[grid_item(w1["id"], x=0, y=0, w=6, h=4), grid_item(w2["id"], x=6, y=0, w=3, h=2)])
        src_before = layout_api.get_layout(src["id"]).json()

        copied = layout_api.copy_layout(src["id"], {"name": unique_name("layout_copy")}).assert_status(201).json()
        cleanup.add("layout copy", lambda: layout_api.delete_layout(copied["id"]))

        copy_grid = layout_api.get_layout(copied["id"]).assert_status(200).json()["grid"]
        copy_widgets = {w["id"]: w for w in layout_api.layout_widgets(copied["id"]).assert_status(200).assert_contract().json()}
        assert len(copy_grid) == 2 and set(copy_widgets) == {c["id"] for c in copy_grid}
        assert not {w1["id"], w2["id"]} & set(copy_widgets), "в копии должны быть НОВЫЕ виджеты, а не ссылки на исходные"

        def signature(grid, widgets_by_id):
            return sorted(
                (c["x"], c["y"], c["w"], c["h"], widgets_by_id[c["id"]]["name"], widgets_by_id[c["id"]]["type"], str(widgets_by_id[c["id"]]["state"]))
                for c in grid
            )

        src_widgets = {w["id"]: w for w in layout_api.layout_widgets(src["id"]).json()}
        assert signature(copy_grid, copy_widgets) == signature(src_before["grid"], src_widgets), "геометрия и настройки виджетов совпадают"
        assert all(w["parent_layout_id"] == copied["id"] and w["access_role"] == "owner" for w in copy_widgets.values())
        assert layout_api.get_layout(src["id"]).json() == src_before, "исходный лейаут не изменился"

    @endpoint(SERVICE, "POST", "/public/v4/layouts/{layout_id}/copy")
    def test_copy_without_name(self, layout_api, layout_factory):
        src = layout_factory()
        layout_api.copy_layout(src["id"], {}).assert_validation_error("name")

    @endpoint(SERVICE, "POST", "/public/v4/layouts/list")
    def test_list_my(self, layout_api, layout_factory):
        layout = layout_factory()
        page = layout_api.list_layouts(pgsize=100, scope="my").assert_status(200).assert_contract().parse(LayoutsPage)
        assert layout["id"] in {i.id for i in page.items}

    @endpoint(SERVICE, "POST", "/public/v4/layouts/list")
    def test_list_filter_by_role(self, layout_api, layout_factory):
        layout_factory()
        page = layout_api.list_layouts(pgsize=100, role=["owner"]).assert_status(200).json()
        assert all(i["access_role"] == "owner" for i in page["items"])
