import allure
import pytest

from framework import endpoint

SERVICE = "auth-manager"


@allure.feature("auth-manager")
@allure.story("user state v2")
class TestUserStateV2:
    @endpoint(SERVICE, "PUT", "/public/v2/users/state")
    @endpoint(SERVICE, "POST", "/public/v2/users/state")
    def test_upsert_and_select(self, auth_api, user_state_keys):
        k1, k2 = user_state_keys(2)
        auth_api.upsert_user_state({k1: {"a": 1}, k2: "value"}).assert_status(200).assert_contract()
        selected = auth_api.select_user_state([k1, k2]).assert_status(200).assert_contract().json()
        assert selected.get(k1) == {"a": 1}
        assert selected.get(k2) == "value"

    @endpoint(SERVICE, "PUT", "/public/v2/users/state")
    def test_upsert_overwrites(self, auth_api, user_state_keys):
        (k,) = user_state_keys(1)
        auth_api.upsert_user_state({k: 1}).assert_status(200)
        auth_api.upsert_user_state({k: 2}).assert_status(200)
        assert auth_api.select_user_state([k]).json().get(k) == 2

    @endpoint(SERVICE, "DELETE", "/public/v2/users/state")
    def test_delete(self, auth_api, user_state_keys):
        k1, k2 = user_state_keys(2)
        auth_api.upsert_user_state({k1: 1, k2: 2}).assert_status(200)
        result = auth_api.delete_user_state([k1]).assert_status(200).assert_contract().json()
        assert result["deleted"] == 1
        remaining = auth_api.select_user_state([k1, k2]).json()
        assert k1 not in remaining and remaining.get(k2) == 2

    @endpoint(SERVICE, "PUT", "/public/v2/users/state")
    def test_upsert_validation(self, auth_api):
        auth_api.request("PUT", "/public/v2/users/state", json_body={}).assert_validation_error("items")

    @endpoint(SERVICE, "POST", "/public/v2/users/state")
    def test_select_unauthorized(self, anon_auth, bad_token):
        anon_auth.with_token(bad_token).select_user_state(["x"]).assert_unauthorized()


@allure.feature("auth-manager")
@allure.story("company state v2")
class TestCompanyStateV2:
    @endpoint(SERVICE, "PUT", "/public/v2/companies/state")
    @endpoint(SERVICE, "POST", "/public/v2/companies/state")
    @endpoint(SERVICE, "DELETE", "/public/v2/companies/state")
    def test_crud(self, auth_api, company_state_keys, me):
        (k,) = company_state_keys(1)
        resp = auth_api.upsert_company_state({k: {"flag": True}})
        if resp.status_code == 403 and me.get("role") != "admin":
            pytest.skip("company state доступен только admin")
        resp.assert_status(200).assert_contract()
        assert auth_api.select_company_state([k]).assert_status(200).json().get(k) == {"flag": True}
        assert auth_api.delete_company_state([k]).assert_status(200).json()["deleted"] == 1


@allure.feature("auth-manager")
@allure.story("user state v1")
class TestUserStateV1:
    @endpoint(SERVICE, "GET", "/public/v1/users/state")
    def test_get_state(self, auth_api):
        auth_api.get_user_state_v1().assert_status(200).assert_contract()
