"""HTTP-слой фреймворка на базе `requests`.

* `ApiClient` — сессия requests с ретраями, таймаутами, логированием и аттачами в Allure.
* `ApiResponse` — обёртка над requests.Response с fluent-проверками.
"""

from __future__ import annotations

import json
import logging
import shlex
import time
import warnings
from collections.abc import Callable
from typing import Any, TypeVar

import requests
from pydantic import BaseModel, TypeAdapter
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config.settings import Settings, get_settings
from framework import openapi
from framework.routing import Service, build_path

try:  # allure необязателен
    import allure
except ImportError:  # pragma: no cover
    allure = None  # type: ignore[assignment]

log = logging.getLogger("api.http")

TOKEN_HEADER = "access-token"
SENSITIVE_HEADERS = {TOKEN_HEADER, "refresh-token", "authorization", "cookie"}
SENSITIVE_FIELDS = {"password", "new_password", "old_password", "access_token", "refresh_token", "jwt_token"}

M = TypeVar("M")


def _mask_headers(headers: dict) -> dict:
    return {k: ("***" if k.lower() in SENSITIVE_HEADERS else v) for k, v in headers.items()}


def _mask_body(body: Any) -> Any:
    if isinstance(body, dict):
        return {k: ("***" if k in SENSITIVE_FIELDS else _mask_body(v)) for k, v in body.items()}
    if isinstance(body, list):
        return [_mask_body(x) for x in body]
    return body


class ApiResponse:
    """Результат вызова API. Все assert_* возвращают self для цепочек."""

    def __init__(self, response: requests.Response, service: Service, method: str, spec_path: str, elapsed: float):
        self.raw = response
        self.service = service
        self.method = method.upper()
        self.spec_path = spec_path
        self.elapsed = elapsed

    # --- доступ к данным ---
    @property
    def status_code(self) -> int:
        return self.raw.status_code

    @property
    def headers(self):
        return self.raw.headers

    @property
    def text(self) -> str:
        return self.raw.text

    def json(self) -> Any:
        try:
            return self.raw.json()
        except ValueError as exc:
            raise AssertionError(f"{self._title()}: ответ не JSON: {self.raw.text[:500]!r}") from exc

    def parse(self, model: type[M] | Any) -> M:
        """Распарсить тело в pydantic-модель (или тип, например list[Model])."""
        if isinstance(model, type) and issubclass(model, BaseModel):
            return model.model_validate(self.json())  # type: ignore[return-value]
        return TypeAdapter(model).validate_python(self.json())

    # --- проверки ---
    def assert_status(self, *expected: int) -> ApiResponse:
        if self.status_code not in expected:
            raise AssertionError(f"{self._title()}: ожидали {' или '.join(map(str, expected))}, получили {self.status_code}\nТело: {self.raw.text[:2000]}")
        return self

    def assert_ok(self) -> ApiResponse:
        if not 200 <= self.status_code < 300:
            self.assert_status(200, 201, 202, 204)
        return self

    def assert_contract(self, fallback_model: Any = None) -> ApiResponse:
        """Сверить статус и тело ответа со спекой сервиса.

        fallback_model — pydantic-модель (или тип), по которой проверить тело, если эндпоинта ещё нет
        в specs/<service>.json (новый эндпоинт из MR до обновления спек). Без неё — ContractError.
        """
        body = None if self.status_code == 204 or not self.raw.content else self.json()
        if fallback_model is not None and not openapi.has_operation(self.service.name, self.method, self.spec_path):
            warnings.warn(f"{self._title()}: нет в спеке, проверено по {fallback_model!r}", stacklevel=2)
            self.parse(fallback_model)
            return self
        openapi.validate_response(self.service.name, self.method, self.spec_path, self.status_code, body)
        return self

    def assert_error(
        self,
        status: int,
        *,
        error_code: str | None = None,
        message_contains: str | None = None,
    ) -> ApiResponse:
        """Проверить единый формат ошибки metapix: {code, status: "error", message, error_code?, fields?}."""
        self.assert_status(status)
        body = self.json()
        assert isinstance(body, dict), f"{self._title()}: ошибка не объект: {body!r}"
        assert body.get("status") == "error", f"{self._title()}: status != 'error': {body}"
        assert body.get("code") == status, f"{self._title()}: code={body.get('code')} != {status}"
        assert isinstance(body.get("message"), str), f"{self._title()}: нет message: {body}"
        if error_code is not None:
            assert body.get("error_code") == error_code, f"{self._title()}: error_code={body.get('error_code')}"
        if message_contains is not None:
            assert message_contains.lower() in body["message"].lower(), f"{self._title()}: message={body['message']!r}"
        return self

    def assert_unauthorized(self) -> ApiResponse:
        """Запрос без/с невалидным токеном. Gateway отвечает 403 INVALID_ACCESS_TOKEN_ERROR,
        сервисы — 401/403 (см. auth-manager errors)."""
        self.assert_status(401, 403)
        return self.assert_error(self.status_code)

    def assert_validation_error(self, *fields: str) -> ApiResponse:
        """422 с перечисленными полями. Gateway кладёт в fields[] `field_name` (первый сегмент: имя поля
        тела или "path"/"query") и `full_path` ("body.filters.scope", "query.timestamp_start") —
        поле считается найденным, если совпало с field_name или с любым сегментом full_path."""
        self.assert_error(422)
        entries = self.json().get("fields") or []
        seen: set[str] = set()
        for e in entries:
            seen.add(str(e.get("field_name")))
            seen.update(str(e.get("full_path") or "").split("."))
        missing = [f for f in fields if f not in seen]
        assert not missing, f"{self._title()}: в 422 нет полей {missing}, есть {entries}"
        return self

    def assert_json(self, predicate: Callable[[Any], bool], message: str = "условие не выполнено") -> ApiResponse:
        assert predicate(self.json()), f"{self._title()}: {message}. Тело: {self.raw.text[:1000]}"
        return self

    def assert_elapsed_lt(self, seconds: float) -> ApiResponse:
        assert self.elapsed < seconds, f"{self._title()}: {self.elapsed:.2f}s >= {seconds}s"
        return self

    def _title(self) -> str:
        return f"{self.method} {self.spec_path} [{self.service.name}]"

    def __repr__(self) -> str:
        return f"<ApiResponse {self._title()} {self.status_code}>"


class ApiClient:
    """Низкоуровневый клиент сервиса. Сервисные клиенты наследуются от него."""

    service: Service

    def __init__(self, service: Service, token: str | None = None, settings: Settings | None = None):
        self.service = service
        self.settings = settings or get_settings()
        self.base_url = self.settings.service_url(service.name)
        self.token = token
        self.session = requests.Session()
        self.session.verify = self.settings.verify_ssl
        retry = Retry(
            total=self.settings.retries,
            backoff_factor=0.5,
            status_forcelist=(502, 503, 504),
            allowed_methods=frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"}),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({"Accept": "application/json", "User-Agent": "metapix-api-tests"})

    # --- фабрики ---
    def with_token(self, token: str | None) -> ApiClient:
        """Копия клиента с другим токеном (None — анонимный)."""
        clone = self.__class__.__new__(self.__class__)
        clone.__dict__.update(self.__dict__)
        clone.token = token
        return clone

    # --- запрос ---
    def request(
        self,
        method: str,
        spec_path: str,
        *,
        path_params: dict | None = None,
        params: dict | list | None = None,
        json_body: Any = None,
        data: Any = None,
        files: Any = None,
        headers: dict | None = None,
        auth: bool = True,
        timeout: float | None = None,
    ) -> ApiResponse:
        url = self.base_url + build_path(self.service, spec_path, self.settings.routing, path_params)
        req_headers = dict(headers or {})
        if auth and self.token and TOKEN_HEADER not in {k.lower() for k in req_headers}:
            req_headers[TOKEN_HEADER] = self.token

        started = time.monotonic()
        response = self.session.request(
            method.upper(),
            url,
            params=params,
            json=json_body,
            data=data,
            files=files,
            headers=req_headers,
            timeout=timeout or self.settings.request_timeout,
        )
        elapsed = time.monotonic() - started
        self._report(response, json_body, elapsed)
        return ApiResponse(response, self.service, method, spec_path, elapsed)

    # --- логирование ---
    def _report(self, response: requests.Response, json_body: Any, elapsed: float) -> None:
        req = response.request
        title = f"{req.method} {req.url} -> {response.status_code} ({elapsed * 1000:.0f} ms)"
        log.info(title)
        if not self.settings.log_bodies:
            return
        limit = self.settings.max_logged_body
        req_body = json.dumps(_mask_body(json_body), ensure_ascii=False, indent=2) if json_body is not None else ""
        try:
            resp_body = json.dumps(_mask_body(response.json()), ensure_ascii=False, indent=2)
        except ValueError:
            resp_body = response.text
        log.debug("request headers: %s\nrequest body: %s", _mask_headers(dict(req.headers)), req_body[:limit])
        log.debug("response body: %s", resp_body[:limit])
        if allure is not None:
            curl = self.to_curl(response.request, json_body)
            allure.attach(
                f"{curl}\n\n--- response {response.status_code} ---\n{resp_body[:limit]}",
                name=title,
                attachment_type=allure.attachment_type.TEXT,
            )

    @staticmethod
    def to_curl(req: requests.PreparedRequest, json_body: Any = None) -> str:
        parts = ["curl", "-X", req.method or "GET", shlex.quote(req.url or "")]
        for k, v in _mask_headers(dict(req.headers)).items():
            parts += ["-H", shlex.quote(f"{k}: {v}")]
        if json_body is not None:
            parts += ["-d", shlex.quote(json.dumps(_mask_body(json_body), ensure_ascii=False))]
        return " ".join(parts)
