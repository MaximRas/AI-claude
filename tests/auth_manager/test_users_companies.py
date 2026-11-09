import allure
import pytest

from framework import endpoint
from framework.data import random_uuid
from services.auth_manager.models import CompanyDetailsOut, CompanyOut, RoleOut, UserCompanySchema, UserOut

SERVICE = "auth-manager"


@allure.feature("auth-manager")
@allure.story("dictionaries")
class TestDictionaries:
    @endpoint(SERVICE, "GET", "/public/roles")
    def test_roles(self, auth_api):
        roles = auth_api.roles().assert_status(200).assert_contract().parse(list[RoleOut])
        assert roles, "список ролей пуст"
        assert len({r.id for r in roles}) == len(roles), "id ролей не уникальны"

    @endpoint(SERVICE, "GET", "/public/v1/company-types")
    def test_company_types(self, auth_api):
        auth_api.company_types().assert_status(200).assert_contract()

    @endpoint(SERVICE, "GET", "/public/roles")
    def test_roles_unauthorized(self, anon_auth, bad_token):
        anon_auth.with_token(bad_token).roles().assert_unauthorized()


@allure.feature("auth-manager")
@allure.story("users")
class TestUsers:
    @pytest.mark.smoke
    @endpoint(SERVICE, "GET", "/public/v1/user")
    def test_current_user(self, auth_api, settings):
        user = auth_api.current_user().assert_status(200).assert_contract().parse(UserOut)
        if settings.test_user_login and "@" in settings.test_user_login:
            assert user.email.lower() == settings.test_user_login.lower()

    @endpoint(SERVICE, "GET", "/public/users")
    def test_users_list_pagination(self, auth_api):
        body = auth_api.users(pgoffset=0, pgsize=2).assert_status(200).assert_contract().json()
        assert len(body["items"]) <= 2
        assert body["pagination"]["offset"] == 0

    @endpoint(SERVICE, "GET", "/public/users/{user_id}")
    def test_get_user_by_id(self, auth_api, me):
        user = auth_api.user(me["id"]).assert_status(200).assert_contract().parse(UserOut)
        assert user.id == me["id"]
        assert user.email == me["email"]

    @endpoint(SERVICE, "GET", "/public/users/{user_id}")
    def test_get_user_not_found(self, auth_api):
        auth_api.user(random_uuid()).assert_status(403, 404)

    @endpoint(SERVICE, "PATCH", "/public/users/{user_id}")
    def test_edit_user_roundtrip(self, auth_api, me, cleanup):
        original = {"first_name": me.get("first_name"), "last_name": me.get("last_name")}
        cleanup.add("restore user name", lambda: auth_api.edit_user(me["id"], {k: v for k, v in original.items() if v}))
        updated = auth_api.edit_user(me["id"], {"first_name": "Autotest"}).assert_status(200).assert_contract().parse(UserOut)
        assert updated.first_name == "Autotest"

    @endpoint(SERVICE, "POST", "/public/v1/company/{company_id}/users")
    def test_company_users(self, auth_api, company):
        body = auth_api.company_users(company["id"], {"pagination": {"pgoffset": 0, "pgsize": 5}})
        body.assert_status(200).assert_contract()

    @endpoint(SERVICE, "POST", "/public/v1/users/check-registered")
    def test_check_registered(self, anon_auth, me):
        resp = anon_auth.check_registered(me["email"]).assert_status(200).assert_contract()
        assert resp.json() is True

    @endpoint(SERVICE, "POST", "/public/v1/users/check-registered")
    def test_check_registered_validation(self, anon_auth):
        anon_auth.request("POST", "/public/v1/users/check-registered", json_body={}, auth=False).assert_validation_error("email")


@allure.feature("auth-manager")
@allure.story("company context")
class TestCompanyContext:
    """После логина токен не привязан к компании: нужен PATCH /context/active-company.
    Контекст хранится per-token, поэтому тесты берут отдельный свежий токен."""

    @pytest.fixture
    def fresh_token(self, token_provider, settings):
        if not (settings.test_user_login and settings.test_user_password):
            pytest.skip("нужны TEST_USER_LOGIN/TEST_USER_PASSWORD")
        return token_provider.login(settings.test_user_login, settings.test_user_password.get_secret_value()).access_token

    @endpoint(SERVICE, "GET", "/public/company")
    def test_company_not_selected(self, anon_auth, fresh_token):
        anon_auth.with_token(fresh_token).company().assert_error(403, error_code="COMPANY_NOT_SELECTED_ERROR")

    @endpoint(SERVICE, "PATCH", "/public/context/active-company")
    def test_select_company(self, anon_auth, fresh_token, settings):
        client = anon_auth.with_token(fresh_token)
        company_id = settings.test_company_id or client.available_companies().json()[0]["id"]
        client.set_active_company(company_id).assert_status(200).assert_contract()
        assert client.company().assert_status(200).json()["id"] == company_id

    @endpoint(SERVICE, "PATCH", "/public/context/active-company")
    def test_select_foreign_company(self, anon_auth, fresh_token):
        client = anon_auth.with_token(fresh_token)
        available = {c["id"] for c in client.available_companies().json()}
        foreign = max(available) + 1_000_000
        resp = client.set_active_company(foreign)
        resp.assert_status(400, 403, 404).assert_error(resp.status_code)

    @endpoint(SERVICE, "PATCH", "/public/context/active-company")
    def test_select_company_validation(self, anon_auth, fresh_token):
        anon_auth.with_token(fresh_token).request("PATCH", "/public/context/active-company", json_body={}).assert_validation_error("company")


@allure.feature("auth-manager")
@allure.story("companies")
class TestCompanies:
    @endpoint(SERVICE, "GET", "/public/company")
    def test_company(self, auth_api, settings):
        company = auth_api.company().assert_status(200).assert_contract().parse(CompanyOut)
        if settings.test_company_id:
            assert company.id == settings.test_company_id

    @endpoint(SERVICE, "GET", "/public/v1/user/company")
    def test_user_company(self, auth_api, company):
        uc = auth_api.user_company().assert_status(200).assert_contract().parse(UserCompanySchema)
        assert uc.id == company["id"]

    @endpoint(SERVICE, "POST", "/public/v1/user/companies")
    def test_user_companies(self, auth_api, company):
        body = auth_api.user_companies({"pagination": {"pgoffset": 0, "pgsize": 50}}).assert_status(200).assert_contract().json()
        assert company["id"] in {c["id"] for c in body["items"]}

    @endpoint(SERVICE, "GET", "/public/context/available-companies")
    def test_available_companies(self, auth_api, company):
        items = auth_api.available_companies().assert_status(200).assert_contract().parse(list[CompanyDetailsOut])
        assert company["id"] in {c.id for c in items}


@allure.feature("auth-manager")
@allure.story("licenses")
class TestLicenses:
    @endpoint(SERVICE, "GET", "/public/licenses")
    def test_licenses(self, auth_api):
        auth_api.licenses().assert_status(200).assert_contract()

    @endpoint(SERVICE, "POST", "/public/v1/licenses/list")
    def test_licenses_list(self, auth_api):
        auth_api.licenses_list({"pagination": {"pgoffset": 0, "pgsize": 5}}).assert_status(200, 403).assert_contract()

    @endpoint(SERVICE, "GET", "/public/v1/gateway_tokens")
    def test_gateway_tokens(self, auth_api):
        auth_api.gateway_tokens(pgoffset=0, pgsize=5).assert_status(200).assert_contract()
