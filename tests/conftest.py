from __future__ import annotations

import logging
import os

import pytest

from config.settings import get_settings
from framework.markers import endpoint_of
from framework.routing import SERVICES, is_exposed

pytest_plugins = [
    "tests.fixtures.clients",
    "tests.fixtures.factories",
]

logging.getLogger("urllib3").setLevel(logging.WARNING)


def pytest_configure(config):
    s = get_settings()
    if s.env_name not in s.available_envs() and not os.getenv("API_BASE_URL"):
        raise pytest.UsageError(f"Неизвестный TEST_ENV={s.env_name!r}: нет секции в config/config.yaml (есть {s.available_envs()}) и не задан API_BASE_URL")
    only_selftest = (config.getoption("markexpr", "") or "").strip() == "selftest"
    if s.production and not s.allow_production and not only_selftest:
        raise pytest.UsageError(f"TEST_ENV={s.env_name} — production. Запуск только с ALLOW_PRODUCTION=true (и TEST_COMPANY_ID изолированной компании)")


def pytest_report_header(config):
    s = get_settings()
    return [
        f"env: {s.env_name}{' [PRODUCTION]' if s.production else ''}  base_url: {s.api_base_url}  web: {s.web_url}  routing: {s.routing.value}",
        f"credentials: {'yes' if s.has_credentials else 'NO (auth tests will be skipped)'}"
        f"  company: {s.test_company_id or 'first available'}"
        f"  second user: {'yes' if s.has_second_user else 'no'}  destructive: {s.allow_destructive}",
    ]


def pytest_collection_modifyitems(config, items):
    s = get_settings()
    for item in items:
        for service, method, path in endpoint_of(item):
            if not is_exposed(SERVICES[service], path, s.routing):
                item.add_marker(pytest.mark.skip(reason=f"{method} {path} недоступен при API_ROUTING={s.routing.value}"))
        if item.get_closest_marker("destructive") and not s.allow_destructive:
            item.add_marker(pytest.mark.skip(reason="destructive: включите ALLOW_DESTRUCTIVE=true"))
        if item.get_closest_marker("user_pool_mutation") and s.prod_user_pool:
            item.add_marker(pytest.mark.skip(reason=f"{s.env_name} смотрит в прод-юзерпул Cognito: создание/удаление пользователей запрещено"))
        if item.get_closest_marker("second_user") and not s.has_second_user:
            item.add_marker(pytest.mark.skip(reason="нужен SECOND_USER_LOGIN/SECOND_USER_PASSWORD"))
        # allure-метки по эндпоинту
        for service, method, path in endpoint_of(item):
            item.add_marker(pytest.mark.allure_label(service, label_type="parentSuite"))
            item.add_marker(pytest.mark.allure_label(f"{method} {path}", label_type="suite"))
