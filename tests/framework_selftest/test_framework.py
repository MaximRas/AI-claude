"""Самотесты фреймворка — работают без стенда (HTTP мокается через `responses`).
Запуск: pytest -m selftest"""

import json

import pytest
import responses

from config.settings import Routing, get_settings
from framework import openapi
from framework.http_client import ApiClient
from framework.routing import AUTH_MANAGER, LAYOUT_MANAGER, OBJECT_MANAGER, EndpointNotExposed, build_path, to_gateway_path

pytestmark = pytest.mark.selftest

BASE = get_settings().api_base_url


@pytest.mark.parametrize(
    "service, spec_path, expected",
    [
        (AUTH_MANAGER, "/public/v1/version", "/auth-manager/v1/version"),
        (AUTH_MANAGER, "/public/auth", "/auth-manager/auth"),
        (AUTH_MANAGER, "/private/health/", "/auth-manager/health/"),
        (LAYOUT_MANAGER, "/private/health", "/layout-manager/health"),
        (LAYOUT_MANAGER, "/public/v4/widgets/{widget_id}", "/layout-manager/v4/widgets/{widget_id}"),
        (OBJECT_MANAGER, "/object-manager/public/v3/objects/{object_id}", "/object-manager/v3/objects/{object_id}"),
        (OBJECT_MANAGER, "/device-manager/public/cameras", "/device-manager/cameras"),
        (OBJECT_MANAGER, "/chartilla/public/v2/chart/{object_type}/{chart_type}", "/chartilla/v2/chart/{object_type}/{chart_type}"),
        (OBJECT_MANAGER, "/watchlist-manager/public/v1/watchlists", "/watchlist-manager/v1/watchlists"),
        (OBJECT_MANAGER, "/object-manager/private/health/", "/object-manager/health/"),
    ],
)
def test_gateway_routing(service, spec_path, expected):
    assert to_gateway_path(service, spec_path) == expected


@pytest.mark.parametrize("spec_path", ["/object-manager/private/v4/objects", "/private/context/acquire/{access_token}"])
def test_private_not_exposed(spec_path):
    with pytest.raises(EndpointNotExposed):
        to_gateway_path(OBJECT_MANAGER, spec_path)


def test_direct_routing_keeps_path():
    assert build_path(OBJECT_MANAGER, "/object-manager/private/v4/objects/{id}", Routing.DIRECT, {"id": 5}) == ("/object-manager/private/v4/objects/5")


def test_path_params_substituted_after_mapping():
    # значение параметра, содержащее "/public/", не должно ломать правила маппинга
    assert build_path(LAYOUT_MANAGER, "/public/v4/widgets/{widget_id}", Routing.GATEWAY, {"widget_id": "x"}) == "/layout-manager/v4/widgets/x"


@responses.activate
def test_client_sends_token_and_parses_error():
    responses.add(
        responses.GET,
        f"{BASE}/layout-manager/v4/widgets/abc",
        json={"code": 404, "status": "error", "message": "Widget not found"},
        status=404,
    )
    client = ApiClient(LAYOUT_MANAGER, token="tkn")
    resp = client.request("GET", "/public/v4/widgets/{widget_id}", path_params={"widget_id": "abc"})
    assert responses.calls[0].request.headers["access-token"] == "tkn"
    resp.assert_error(404, message_contains="not found")


@responses.activate
def test_anonymous_client_has_no_token():
    responses.add(responses.GET, f"{BASE}/auth-manager/me", json={"code": 403, "status": "error", "message": "Missing"}, status=403)
    resp = ApiClient(AUTH_MANAGER, token="tkn").with_token(None).request("GET", "/public/me")
    assert "access-token" not in responses.calls[0].request.headers
    resp.assert_unauthorized()


@responses.activate
def test_assert_status_message_contains_body():
    responses.add(responses.GET, f"{BASE}/auth-manager/v1/version", body="boom", status=500)
    resp = ApiClient(AUTH_MANAGER).request("GET", "/public/v1/version", auth=False)
    with pytest.raises(AssertionError, match="boom"):
        resp.assert_status(200)


@responses.activate
def test_validation_error_fields():
    responses.add(
        responses.POST,
        f"{BASE}/auth-manager/auth",
        json={
            "code": 422,
            "status": "error",
            "message": "login:field required",
            "fields": [{"field_name": "login", "msg": "field required", "type": "value_error.missing"}],
        },
        status=422,
    )
    resp = ApiClient(AUTH_MANAGER).request("POST", "/public/auth", json_body={}, auth=False)
    resp.assert_validation_error("login")
    with pytest.raises(AssertionError):
        resp.assert_validation_error("password")


def test_curl_masks_token():
    import requests

    req = requests.Request("POST", "https://x/y", headers={"access-token": "secret"}, json={"password": "p"}).prepare()
    curl = ApiClient.to_curl(req, {"password": "p", "login": "l"})
    assert "secret" not in curl and '"p"' not in curl and "***" in curl


# ---------------- contract ----------------

SPEC = {
    "openapi": "3.1.0",
    "paths": {
        "/public/items/{id}": {
            "get": {
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Item"}}}},
                    "404 ": {"description": "not found"},
                    "422": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/HTTPValidationError"}}}},
                }
            }
        }
    },
    "components": {
        "schemas": {
            "Item": {
                "type": "object",
                "required": ["id", "tags"],
                "properties": {
                    "id": {"type": "integer"},
                    "parent_id": {"type": "integer"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                    "kind": {"allOf": [{"$ref": "#/components/schemas/Kind"}], "default": "a"},
                },
            },
            "Kind": {"enum": ["a", "b"]},
            "HTTPValidationError": {"type": "object"},
        }
    },
}


@pytest.fixture
def fake_spec(tmp_path, monkeypatch):
    (tmp_path / "auth-manager.json").write_text(json.dumps(SPEC))
    monkeypatch.setattr(get_settings(), "specs_dir", tmp_path)
    openapi.load_spec.cache_clear()
    openapi._normalized_components.cache_clear()
    yield
    openapi.load_spec.cache_clear()
    openapi._normalized_components.cache_clear()


def test_contract_ok_with_nullable_optional(fake_spec):
    openapi.validate_response("auth-manager", "GET", "/public/items/{id}", 200, {"id": 1, "tags": [], "parent_id": None, "kind": "b"})


def test_contract_extra_fields_allowed(fake_spec):
    openapi.validate_response("auth-manager", "GET", "/public/items/{id}", 200, {"id": 1, "tags": [], "new_field": 1})


@pytest.mark.parametrize(
    "body, fragment",
    [
        ({"tags": []}, "'id' is a required property"),
        ({"id": "1", "tags": []}, "is not of type 'integer'"),
        ({"id": 1, "tags": [], "kind": "z"}, "kind"),
        ({"id": None, "tags": []}, "id"),
    ],
)
def test_contract_violations(fake_spec, body, fragment):
    with pytest.raises(openapi.ContractError, match=fragment):
        openapi.validate_response("auth-manager", "GET", "/public/items/{id}", 200, body)


def test_contract_status_with_trailing_space_key(fake_spec):
    openapi.validate_response("auth-manager", "GET", "/public/items/{id}", 404, {"code": 404})


def test_contract_undocumented_status(fake_spec):
    with pytest.raises(openapi.ContractError, match="не задокументирован"):
        openapi.validate_response("auth-manager", "GET", "/public/items/{id}", 500, {})


def test_contract_unknown_operation(fake_spec):
    with pytest.raises(openapi.ContractError, match="отсутствует"):
        openapi.validate_response("auth-manager", "POST", "/public/items/{id}", 200, {})


@responses.activate
def test_contract_fallback_model_for_new_endpoint(fake_spec):
    from pydantic import BaseModel

    class New(BaseModel):
        id: int

    responses.add(responses.GET, f"{BASE}/auth-manager/new/1", json={"id": 1}, status=200)
    resp = ApiClient(AUTH_MANAGER).request("GET", "/public/new/{id}", path_params={"id": 1}, auth=False)
    with pytest.warns(UserWarning, match="нет в спеке"):
        resp.assert_contract(fallback_model=New)
    with pytest.raises(openapi.ContractError):
        resp.assert_contract()


@responses.activate
def test_validation_error_full_path():
    responses.add(
        responses.GET,
        f"{BASE}/layout-manager/detailing",
        json={
            "code": 422,
            "status": "error",
            "message": "query:field required",
            "fields": [{"field_name": "query", "full_path": "query.timestamp_start", "msg": "field required"}],
        },
        status=422,
    )
    resp = ApiClient(LAYOUT_MANAGER).request("GET", "/public/detailing", auth=False)
    resp.assert_validation_error("timestamp_start")
    with pytest.raises(AssertionError):
        resp.assert_validation_error("timestamp_end")
