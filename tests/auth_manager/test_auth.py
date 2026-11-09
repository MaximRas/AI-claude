import allure
import pytest

from framework import endpoint
from framework.data import unique_name
from services.auth_manager.models import AuthOut, MeOut, VersionSchema

SERVICE = "auth-manager"


@allure.feature("auth-manager")
@allure.story("health / version")
class TestGeneral:
    @pytest.mark.smoke
    @endpoint(SERVICE, "GET", "/private/health/")
    def test_health(self, anon_auth):
        body = anon_auth.health().assert_status(200).json()
        assert body["type"] == "auth-manager"
        assert body["uptime"] >= 0

    @pytest.mark.smoke
    @endpoint(SERVICE, "GET", "/public/v1/version")
    def test_version(self, anon_auth):
        version = anon_auth.version().assert_status(200).assert_contract().parse(VersionSchema)
        assert len(version.commit) == 40


@allure.feature("auth-manager")
@allure.story("login")
class TestLogin:
    @pytest.mark.smoke
    @endpoint(SERVICE, "POST", "/public/auth")
    def test_login_success(self, anon_auth, settings):
        if not (settings.test_user_login and settings.test_user_password):
            pytest.skip("нужны TEST_USER_LOGIN/TEST_USER_PASSWORD")
        resp = anon_auth.auth(settings.test_user_login, settings.test_user_password.get_secret_value())
        tokens = resp.assert_status(200).assert_contract().parse(AuthOut)
        assert tokens.access_token.count(".") == 2, "access_token должен быть JWT"
        assert tokens.refresh_token

    @endpoint(SERVICE, "POST", "/public/auth")
    def test_login_wrong_password(self, anon_auth, settings):
        login = settings.test_user_login or f"{unique_name('user')}@example.com"
        resp = anon_auth.auth(login, "definitely-wrong-password")
        resp.assert_status(400, 401, 403).assert_error(resp.status_code)

    @endpoint(SERVICE, "POST", "/public/auth")
    def test_login_unknown_user(self, anon_auth):
        resp = anon_auth.auth(f"{unique_name('nouser')}@example.com", "whatever")
        resp.assert_status(400, 401, 403, 404).assert_error(resp.status_code)

    @pytest.mark.parametrize(
        "login, password, missing",
        [(None, "x", ["login"]), ("x@example.com", None, ["password"]), (None, None, ["login", "password"])],
        ids=["no_login", "no_password", "empty_body"],
    )
    @endpoint(SERVICE, "POST", "/public/auth")
    def test_login_validation(self, anon_auth, login, password, missing):
        anon_auth.auth(login, password).assert_validation_error(*missing)


@allure.feature("auth-manager")
@allure.story("token")
class TestToken:
    @pytest.mark.smoke
    @endpoint(SERVICE, "GET", "/public/me")
    def test_me(self, auth_api, main_tokens):
        me = auth_api.me().assert_status(200).assert_contract().parse(MeOut)
        if main_tokens.user_id:
            assert me.user_id == main_tokens.user_id

    @endpoint(SERVICE, "GET", "/public/me")
    def test_me_unauthorized(self, anon_auth, bad_token):
        anon_auth.with_token(bad_token).me().assert_unauthorized()

    @endpoint(SERVICE, "POST", "/public/auth/refresh-token")
    def test_refresh_token(self, anon_auth, token_provider, settings):
        if not (settings.test_user_login and settings.test_user_password):
            pytest.skip("нужен логин/пароль (refresh_token не доступен при TEST_ACCESS_TOKEN)")
        # отдельный логин, чтобы не инвалидировать сессионный токен
        fresh = token_provider.login(settings.test_user_login, settings.test_user_password.get_secret_value())
        new = anon_auth.refresh_token(fresh.access_token, fresh.refresh_token).assert_status(200).assert_contract().parse(AuthOut)
        assert new.access_token
        anon_auth.with_token(new.access_token).me().assert_status(200)

    @endpoint(SERVICE, "POST", "/public/auth/refresh-token")
    def test_refresh_token_invalid(self, anon_auth):
        from tests.fixtures.clients import INVALID_JWT

        anon_auth.refresh_token(INVALID_JWT, "invalid-refresh").assert_unauthorized()
