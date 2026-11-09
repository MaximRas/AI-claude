"""Шаринг виджетов и лейаутов. Сценарии с проверкой прав второго пользователя
требуют SECOND_USER_LOGIN/SECOND_USER_PASSWORD (маркер second_user)."""

import allure
import pytest

from framework import endpoint
from services.auth_manager.client import AuthManagerClient
from services.layout_manager.models import AccessEntry
from tests.fixtures.factories import grid_item

SERVICE = "layout-manager"


def _ep(method: str, suffix: str = ""):
    return [
        endpoint(SERVICE, method, f"/public/v4/widgets/{{widget_id}}/access{suffix}"),
        endpoint(SERVICE, method, f"/public/v4/layouts/{{layout_id}}/access{suffix}"),
    ]


def _params(method: str, suffix: str = ""):
    w, l_ = _ep(method, suffix)
    return [pytest.param("widgets", marks=w, id="widgets"), pytest.param("layouts", marks=l_, id="layouts")]


@pytest.fixture
def entity(widget_factory, layout_factory):
    """Создаёт виджет или лейаут в зависимости от параметра kind."""

    def make(kind: str) -> str:
        return (widget_factory() if kind == "widgets" else layout_factory())["id"]

    return make


@allure.feature("layout-manager")
@allure.story("access")
class TestAccess:
    @pytest.mark.parametrize("kind", _params("GET"))
    def test_owner_access_list(self, layout_api, entity, kind):
        entries = layout_api.get_access(kind, entity(kind)).assert_status(200).assert_contract().parse(list[AccessEntry])
        assert all(e.role.value in {"viewer", "editor", "owner"} for e in entries)

    @pytest.mark.parametrize("kind", _params("POST"))
    def test_grant_company_viewer(self, layout_api, entity, kind):
        entity_id = entity(kind)
        entry = layout_api.grant_access(kind, entity_id, scope="company", role="viewer").assert_status(201).assert_contract().parse(AccessEntry)
        assert entry.scope.value == "company" and entry.role.value == "viewer"
        ids = {e["id"] for e in layout_api.get_access(kind, entity_id).json()}
        assert entry.id in ids

    @pytest.mark.parametrize("kind", _params("POST"))
    def test_grant_user_scope_without_user_id(self, layout_api, entity, kind):
        # alphatest1 22.10.2026: сейчас отвечает 500 Internal Server Error — дефект, ожидаем 400/422
        layout_api.grant_access(kind, entity(kind), scope="user", role="viewer").assert_status(400, 422)

    @pytest.mark.parametrize("kind", _params("POST"))
    def test_grant_invalid_role(self, layout_api, entity, kind):
        layout_api.grant_access(kind, entity(kind), scope="company", role="superuser").assert_status(422)

    @pytest.mark.parametrize("kind", _params("PATCH", "/{entry_id}"))
    def test_patch_role(self, layout_api, entity, kind):
        entity_id = entity(kind)
        entry = layout_api.grant_access(kind, entity_id, scope="company", role="viewer").assert_status(201).json()
        patched = layout_api.patch_access(kind, entity_id, entry["id"], "editor").assert_status(200).assert_contract().json()
        assert patched["role"] == "editor"

    @pytest.mark.parametrize("kind", _params("DELETE", "/{entry_id}"))
    def test_revoke_entry(self, layout_api, entity, kind):
        entity_id = entity(kind)
        entry = layout_api.grant_access(kind, entity_id, scope="company", role="viewer").assert_status(201).json()
        layout_api.revoke_access(kind, entity_id, entry["id"]).assert_status(204)
        assert entry["id"] not in {e["id"] for e in layout_api.get_access(kind, entity_id).json()}

    @pytest.mark.parametrize("kind", _params("DELETE"))
    def test_revoke_all_company(self, layout_api, entity, kind):
        entity_id = entity(kind)
        layout_api.grant_access(kind, entity_id, scope="company", role="viewer").assert_status(201)
        layout_api.revoke_all_access(kind, entity_id, mode="company").assert_status(204)
        assert not [e for e in layout_api.get_access(kind, entity_id).json() if e["scope"] == "company"]

    @pytest.mark.parametrize("kind", _params("DELETE"))
    @pytest.mark.parametrize("scope", ["company"])
    def test_is_shared_follows_access(self, layout_api, entity, kind, scope):
        """is_shared вычисляется по access-записям (после MR legacy-колонка layout.shared больше не пишется)."""
        entity_id = entity(kind)
        get = layout_api.get_widget if kind == "widgets" else layout_api.get_layout
        assert get(entity_id).json()["is_shared"] is False, "новая сущность не расшарена"
        layout_api.grant_access(kind, entity_id, scope=scope, role="viewer").assert_status(201)
        assert get(entity_id).json()["is_shared"] is True
        layout_api.revoke_all_access(kind, entity_id, mode="all").assert_status(204)
        assert get(entity_id).json()["is_shared"] is False, "после снятия шаринга сущность снова закрыта"

    @endpoint(SERVICE, "POST", "/public/v4/layouts/{layout_id}/access")
    def test_layout_share_propagates_to_embedded_widgets(self, layout_api, layout_factory, widget_factory):
        w = widget_factory()
        layout = layout_factory(grid=[grid_item(w["id"])])
        layout_api.grant_access("layouts", layout["id"], scope="company", role="viewer").assert_status(201)
        assert layout_api.get_widget(w["id"]).json()["is_shared"] is True
        assert all(x["is_shared"] for x in layout_api.layout_widgets(layout["id"]).json())

    @endpoint(SERVICE, "POST", "/public/v4/widgets/{widget_id}/access")
    def test_embedded_widget_cannot_be_shared_separately(self, layout_api, layout_factory, widget_factory):
        w = widget_factory()
        layout_factory(grid=[grid_item(w["id"])])
        layout_api.grant_access("widgets", w["id"], scope="company", role="viewer").assert_error(400, message_contains="cannot be shared")

    @pytest.mark.parametrize("kind", _params("GET"))
    def test_shared_flag_in_lists(self, layout_api, entity, kind):
        entity_id = entity(kind)
        layout_api.grant_access(kind, entity_id, scope="company", role="editor").assert_status(201)
        lister = layout_api.list_widgets if kind == "widgets" else layout_api.list_layouts
        items = {i["id"]: i for i in lister(pgsize=100, scope="my").assert_status(200).json()["items"]}
        assert items[entity_id]["is_shared"] is True and items[entity_id]["access_role"] == "owner"

    @pytest.mark.parametrize("kind", _params("DELETE"))
    def test_revoke_all_invalid_mode(self, layout_api, entity, kind):
        layout_api.revoke_all_access(kind, entity(kind), mode="nobody").assert_status(422)


@allure.feature("layout-manager")
@allure.story("access: second user")
@pytest.mark.second_user
class TestAccessSecondUser:
    @pytest.mark.parametrize("kind", _params("POST"))
    def test_viewer_can_read_but_not_edit(self, layout_api, layout_api_second, entity, kind):
        entity_id = entity(kind)
        uid = AuthManagerClient(layout_api_second.token).me().assert_status(200).json()["user_id"]
        layout_api.grant_access(kind, entity_id, scope="user", role="viewer", user_id=uid).assert_status(201)

        get = layout_api_second.get_widget if kind == "widgets" else layout_api_second.get_layout
        edit = layout_api_second.edit_widget if kind == "widgets" else layout_api_second.modify_layout
        item = get(entity_id).assert_status(200).json()
        assert item["access_role"] == "viewer"
        assert item["is_shared"] is True
        edit(entity_id, {"name": "hacked"}).assert_status(403, 404)

    @pytest.mark.parametrize(
        "kind",
        [
            pytest.param("widgets", marks=endpoint(SERVICE, "GET", "/public/v4/widgets/{widget_id}"), id="widgets"),
            pytest.param("layouts", marks=endpoint(SERVICE, "GET", "/public/v4/layouts/{layout_id}"), id="layouts"),
        ],
    )
    def test_no_access_without_grant(self, layout_api_second, entity, kind):
        entity_id = entity(kind)
        get = layout_api_second.get_widget if kind == "widgets" else layout_api_second.get_layout
        get(entity_id).assert_status(403, 404)
