"""Получение access-token через auth-manager и кэширование на сессию pytest."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

from config.settings import Settings, get_settings
from framework.http_client import ApiClient
from framework.routing import AUTH_MANAGER

log = logging.getLogger("api.auth")

AUTH_PATH = "/public/auth"
REFRESH_PATH = "/public/auth/refresh-token"
AVAILABLE_COMPANIES_PATH = "/public/context/available-companies"
ACTIVE_COMPANY_PATH = "/public/context/active-company"


@dataclass
class Tokens:
    access_token: str
    refresh_token: str | None
    user_id: str | None


class AuthError(RuntimeError):
    pass


class TokenProvider:
    """Логинится один раз на пользователя и отдаёт токен из кэша."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._cache: dict[str, Tokens] = {}
        self._lock = threading.Lock()

    def login(self, login: str, password: str) -> Tokens:
        client = ApiClient(AUTH_MANAGER, settings=self.settings)
        resp = client.request("POST", AUTH_PATH, json_body={"login": login, "password": password}, auth=False)
        if resp.status_code != 200:
            raise AuthError(f"Логин {login!r} не удался: {resp.status_code} {resp.text[:300]}")
        body = resp.json()
        return Tokens(body["access_token"], body.get("refresh_token"), body.get("user_id"))

    def select_company(self, access_token: str, company_id: int | None = None) -> int:
        """Привязать токен к компании (контекст хранится на стороне сервера per-token).
        Без company_id берётся первая доступная компания."""
        client = ApiClient(AUTH_MANAGER, token=access_token, settings=self.settings)
        if company_id is None:
            companies = client.request("GET", AVAILABLE_COMPANIES_PATH).assert_status(200).json()
            if not companies:
                raise AuthError("У пользователя нет доступных компаний")
            company_id = companies[0]["id"]
            log.warning("TEST_COMPANY_ID не задан — выбрана компания %s (%s)", company_id, companies[0].get("name"))
        resp = client.request("PATCH", ACTIVE_COMPANY_PATH, json_body={"company": company_id})
        if resp.status_code != 200:
            raise AuthError(f"Не удалось выбрать компанию {company_id}: {resp.status_code} {resp.text[:300]}")
        return company_id

    def refresh(self, tokens: Tokens) -> Tokens:
        client = ApiClient(AUTH_MANAGER, settings=self.settings)
        resp = client.request(
            "POST",
            REFRESH_PATH,
            headers={"access-token": tokens.access_token, "refresh-token": tokens.refresh_token or ""},
            auth=False,
        )
        resp.assert_status(200)
        body = resp.json()
        return Tokens(body["access_token"], body.get("refresh_token"), body.get("user_id"))

    def tokens_for(self, login: str, password: str) -> Tokens:
        with self._lock:
            if login not in self._cache:
                tokens = self.login(login, password)
                self.select_company(tokens.access_token, self.settings.test_company_id)
                self._cache[login] = tokens
            return self._cache[login]

    def main_user(self) -> Tokens:
        s = self.settings
        if s.test_access_token:
            token = s.test_access_token.get_secret_value()
            if s.test_company_id is not None:
                with self._lock:
                    if "__static__" not in self._cache:
                        self.select_company(token, s.test_company_id)
                        self._cache["__static__"] = Tokens(token, None, None)
            return Tokens(token, None, None)
        if not (s.test_user_login and s.test_user_password):
            raise AuthError("Не заданы TEST_USER_LOGIN/TEST_USER_PASSWORD или TEST_ACCESS_TOKEN")
        return self.tokens_for(s.test_user_login, s.test_user_password.get_secret_value())

    def main_user_in_company(self, company_id: int) -> Tokens:
        """Отдельный токен основного пользователя, привязанный к другой компании (контекст — per-token)."""
        s = self.settings
        if not (s.test_user_login and s.test_user_password):
            raise AuthError("Нужны TEST_USER_LOGIN/TEST_USER_PASSWORD")
        key = f"{s.test_user_login}@{company_id}"
        with self._lock:
            if key not in self._cache:
                tokens = self.login(s.test_user_login, s.test_user_password.get_secret_value())
                self.select_company(tokens.access_token, company_id)
                self._cache[key] = tokens
            return self._cache[key]

    def second_user(self) -> Tokens:
        s = self.settings
        if not (s.second_user_login and s.second_user_password):
            raise AuthError("Не заданы SECOND_USER_LOGIN/SECOND_USER_PASSWORD")
        return self.tokens_for(s.second_user_login, s.second_user_password.get_secret_value())
