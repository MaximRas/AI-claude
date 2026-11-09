"""Фикстуры клиентов. Суффикс `_api` — клиент с токеном основного пользователя,
`anon_*` — без токена (для негативных проверок авторизации)."""

from __future__ import annotations

import pytest

from config.settings import Settings, get_settings
from framework.auth import AuthError, TokenProvider, Tokens
from framework.cleanup import Cleanup
from services.auth_manager.client import AuthManagerClient
from services.layout_manager.client import LayoutManagerClient
from services.object_manager.client import (
    ChartillaClient,
    DeviceManagerClient,
    ObjectManagerClient,
    ObjectManagerPrivateClient,
    WatchlistManagerClient,
)

INVALID_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhdXRvdGVzdCJ9.c2lnbmF0dXJl"


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest.fixture(scope="session")
def token_provider(settings) -> TokenProvider:
    return TokenProvider(settings)


@pytest.fixture(scope="session")
def main_tokens(token_provider, settings) -> Tokens:
    if not settings.has_credentials:
        pytest.skip("Нет TEST_USER_LOGIN/TEST_USER_PASSWORD (или TEST_ACCESS_TOKEN)")
    try:
        return token_provider.main_user()
    except AuthError as exc:
        pytest.fail(str(exc))


@pytest.fixture(scope="session")
def second_tokens(token_provider, settings) -> Tokens:
    if not settings.has_second_user:
        pytest.skip("Нет SECOND_USER_LOGIN/SECOND_USER_PASSWORD")
    return token_provider.second_user()


@pytest.fixture(scope="session")
def token(main_tokens) -> str:
    return main_tokens.access_token


# --- анонимные клиенты (без токена) ---
@pytest.fixture(scope="session")
def anon_auth() -> AuthManagerClient:
    return AuthManagerClient()


@pytest.fixture(scope="session")
def anon_om() -> ObjectManagerClient:
    return ObjectManagerClient()


@pytest.fixture(scope="session")
def anon_devices() -> DeviceManagerClient:
    return DeviceManagerClient()


@pytest.fixture(scope="session")
def anon_watchlists() -> WatchlistManagerClient:
    return WatchlistManagerClient()


@pytest.fixture(scope="session")
def anon_chartilla() -> ChartillaClient:
    return ChartillaClient()


@pytest.fixture(scope="session")
def anon_layout() -> LayoutManagerClient:
    return LayoutManagerClient()


# --- авторизованные клиенты ---
@pytest.fixture(scope="session")
def auth_api(token) -> AuthManagerClient:
    return AuthManagerClient(token)


@pytest.fixture(scope="session")
def objects_token(token, token_provider, settings) -> str:
    """Токен для object-manager/chartilla: в компании с реальными объектами (api_tests.objects_company_id)."""
    cid = settings.objects_company_id
    if cid is None or cid == settings.test_company_id:
        return token
    return token_provider.main_user_in_company(cid).access_token


@pytest.fixture(scope="session")
def om_api(objects_token) -> ObjectManagerClient:
    return ObjectManagerClient(objects_token)


@pytest.fixture(scope="session")
def devices_api(token) -> DeviceManagerClient:
    return DeviceManagerClient(token)


@pytest.fixture(scope="session")
def watchlists_api(token) -> WatchlistManagerClient:
    return WatchlistManagerClient(token)


@pytest.fixture(scope="session")
def chartilla_api(objects_token) -> ChartillaClient:
    return ChartillaClient(objects_token)


@pytest.fixture(scope="session")
def layout_api(token) -> LayoutManagerClient:
    return LayoutManagerClient(token)


@pytest.fixture(scope="session")
def layout_api_second(second_tokens) -> LayoutManagerClient:
    return LayoutManagerClient(second_tokens.access_token)


@pytest.fixture(scope="session")
def om_private() -> ObjectManagerPrivateClient:
    return ObjectManagerPrivateClient()


@pytest.fixture(scope="session")
def me(auth_api) -> dict:
    """Текущий пользователь (GET /public/v1/user)."""
    return auth_api.current_user().assert_status(200).json()


@pytest.fixture(scope="session")
def company(auth_api) -> dict:
    return auth_api.company().assert_status(200).json()


@pytest.fixture
def cleanup():
    c = Cleanup()
    yield c
    c.run()


@pytest.fixture(params=["missing", "invalid"], ids=["no_token", "invalid_token"])
def bad_token(request) -> str | None:
    """Параметризация для негативных auth-проверок: без токена и с невалидным JWT."""
    return None if request.param == "missing" else INVALID_JWT
