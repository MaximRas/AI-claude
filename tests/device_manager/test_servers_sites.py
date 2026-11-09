"""Servers / sites. В API нет DELETE — созданные сущности остаются на стенде,
поэтому тесты на создание помечены `destructive`. Чтение списков — безопасно."""

import allure
import pytest

from framework import endpoint
from framework.data import random_uuid, unique_name

SERVICE = "object-manager"

KINDS = [
    pytest.param("server", marks=endpoint(SERVICE, "POST", "/device-manager/public/servers"), id="servers"),
    pytest.param("site", marks=endpoint(SERVICE, "POST", "/device-manager/public/sites"), id="sites"),
]


def _ops(api, kind):
    return {
        "create": getattr(api, f"create_{kind}"),
        "list": getattr(api, f"list_{kind}s"),
        "get": getattr(api, f"get_{kind}"),
        "update": getattr(api, f"update_{kind}"),
    }


@allure.feature("device-manager")
@allure.story("servers / sites")
class TestServersSitesRead:
    @endpoint(SERVICE, "POST", "/device-manager/public/servers/list")
    def test_list_servers(self, devices_api):
        body = devices_api.list_servers(pgsize=5).assert_status(200).assert_contract().json()
        assert len(body["items"]) <= 5

    @endpoint(SERVICE, "POST", "/device-manager/public/sites/list")
    def test_list_sites(self, devices_api):
        body = devices_api.list_sites(pgsize=5).assert_status(200).assert_contract().json()
        assert len(body["items"]) <= 5

    @endpoint(SERVICE, "GET", "/device-manager/public/servers/{external_uuid}")
    def test_get_server_not_found(self, devices_api):
        devices_api.get_server(random_uuid()).assert_error(404)

    @endpoint(SERVICE, "GET", "/device-manager/public/sites/{external_uuid}")
    def test_get_site_not_found(self, devices_api):
        devices_api.get_site(random_uuid()).assert_error(404)

    @endpoint(SERVICE, "POST", "/device-manager/public/servers")
    def test_create_server_validation(self, devices_api):
        devices_api.request("POST", "/device-manager/public/servers", json_body={"name": "x"}).assert_validation_error("external_uuid")

    @endpoint(SERVICE, "POST", "/device-manager/public/sites")
    def test_create_site_invalid_uuid(self, devices_api):
        devices_api.create_site("not-a-uuid", "x").assert_validation_error("external_uuid")


@allure.feature("device-manager")
@allure.story("servers / sites")
@pytest.mark.destructive
class TestServersSitesWrite:
    @pytest.mark.parametrize(
        "kind",
        [
            pytest.param(
                "server",
                marks=[
                    endpoint(SERVICE, "POST", "/device-manager/public/servers"),
                    endpoint(SERVICE, "GET", "/device-manager/public/servers/{external_uuid}"),
                    endpoint(SERVICE, "PATCH", "/device-manager/public/servers/{external_uuid}"),
                ],
                id="server",
            ),
            pytest.param(
                "site",
                marks=[
                    endpoint(SERVICE, "POST", "/device-manager/public/sites"),
                    endpoint(SERVICE, "GET", "/device-manager/public/sites/{external_uuid}"),
                    endpoint(SERVICE, "PATCH", "/device-manager/public/sites/{external_uuid}"),
                ],
                id="site",
            ),
        ],
    )
    def test_create_get_update(self, devices_api, kind):
        ops = _ops(devices_api, kind)
        ext, name = random_uuid(), unique_name(kind)
        created = ops["create"](ext, name).assert_status(200).assert_contract().json()
        assert created["external_uuid"] == ext and created["name"] == name

        assert ops["get"](ext).assert_status(200).assert_contract().json()["name"] == name

        new_name = unique_name(f"{kind}_renamed")
        updated = ops["update"](ext, new_name).assert_status(200).assert_contract().json()
        assert updated["name"] == new_name
        assert updated["updated_at"]

    @pytest.mark.parametrize("kind", KINDS)
    def test_create_duplicate(self, devices_api, kind):
        ops = _ops(devices_api, kind)
        ext = random_uuid()
        ops["create"](ext, unique_name(kind)).assert_status(200)
        ops["create"](ext, unique_name(kind)).assert_status(400, 409)
