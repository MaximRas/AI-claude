"""Настройки тестового прогона.

Приоритет (сверху вниз):
  1. переменные окружения (в GitLab CI — CI/CD variables);
  2. .env в корне проекта (локально, не коммитится; пример — .env.example);
  3. config/config.yaml — окружения (тот же формат, что у фронтовых автотестов), секция TEST_ENV; коммитится, без секретов;
  4. значения по умолчанию ниже.
TEST_ENV по умолчанию — alphatest1. Вложенные поля из ENV — через "__": COGNITO__SECRET_KEY.
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

import yaml
from pydantic import BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, PydanticBaseSettingsSource, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_YAML = ROOT_DIR / "config" / "config.yaml"
TEST_ENV = os.getenv("TEST_ENV", "alphatest1").strip() or "alphatest1"
# Ключи верхнего уровня config.yaml, которые НЕ являются окружениями
_GLOBAL_KEYS = {"gitlab", "requests_timeout", "mailinator", "DWNX"}


def load_config_yaml(path: Path = CONFIG_YAML) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def config_environments(path: Path = CONFIG_YAML) -> list[str]:
    return sorted(k for k, v in load_config_yaml(path).items() if k not in _GLOBAL_KEYS and not k.startswith("_") and isinstance(v, dict))


class ConfigYamlSource(PydanticBaseSettingsSource):
    """Плоская проекция config.yaml (глобальные ключи + секция TEST_ENV) на поля Settings."""

    def __init__(self, settings_cls, env_name: str, path: Path = CONFIG_YAML):
        super().__init__(settings_cls)
        self.env_name = env_name
        self.path = path

    def get_field_value(self, field, field_name):  # не используется: всё отдаём в __call__
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        raw = load_config_yaml(self.path)
        env = raw.get(self.env_name)
        out: dict[str, Any] = {}
        if timeout := raw.get("requests_timeout"):
            out["request_timeout"] = timeout
        if host := (raw.get("gitlab") or {}).get("host"):
            out["gitlab_host"] = host
        if dwnx := raw.get("DWNX"):
            out["dwnx"] = {k: v for k, v in dwnx.items() if k != "password"}
        if not isinstance(env, dict):
            return out
        mapping = {"url": "api_base_url", "web_url": "web_url", "theme": "theme"}
        for src, dst in mapping.items():
            if env.get(src) is not None:
                out[dst] = env[src]
        for block in ("cognito", "license_server", "service_provider"):
            if isinstance(env.get(block), dict):
                # секреты из yaml игнорируем намеренно — только через ENV
                out[block] = {k: v for k, v in env[block].items() if k not in {"access_key", "secret_key"}}
        api = env.get("api_tests") or {}
        if api.get("routing"):
            out["routing"] = api["routing"]
        if api.get("company_id") is not None:
            out["test_company_id"] = api["company_id"]
        if api.get("production") is not None:
            out["production"] = api["production"]
        if api.get("objects_company_id") is not None:
            out["objects_company_id"] = api["objects_company_id"]
        if api.get("prod_user_pool") is not None:
            out["prod_user_pool"] = api["prod_user_pool"]
        return out


class Cognito(BaseModel):
    region_name: str | None = None
    user_pool_id: str | None = None
    app_id: str | None = None
    access_key: SecretStr | None = None  # env: COGNITO__ACCESS_KEY
    secret_key: SecretStr | None = None  # env: COGNITO__SECRET_KEY


class LicenseServer(BaseModel):
    web_url: str | None = None
    api_url: str | None = None
    service_provider: str | None = None
    integrator: str | None = None


class ServiceProvider(BaseModel):
    company_name_cpo: str | None = None
    company_name_euo: str | None = None
    company_name_integrator: str | None = None
    email: str | None = None


class DwNxAccount(BaseModel):
    email: str | None = None
    name: str | None = None
    password: SecretStr | None = None  # env: DWNX__PASSWORD


class Routing(str, Enum):
    """Как путь из OpenAPI превращается в URL.

    gateway — запросы идут через API gateway стенда
              (https://api.<env>/...): сегмент `/public` из пути спеки убирается,
              `/private/*` (кроме health) снаружи недоступны.
    direct  — запросы идут напрямую в сервис (локальный docker-compose,
              port-forward в k8s): путь спеки используется как есть.
    """

    GATEWAY = "gateway"
    DIRECT = "direct"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        populate_by_name=True,
    )

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
        env_name = os.getenv("TEST_ENV") or _dotenv_value("TEST_ENV") or TEST_ENV
        return init_settings, env_settings, dotenv_settings, ConfigYamlSource(settings_cls, env_name), file_secret_settings

    # --- окружение ---
    env_name: str = Field(default_factory=lambda: os.getenv("TEST_ENV") or _dotenv_value("TEST_ENV") or TEST_ENV, alias="TEST_ENV")
    api_base_url: str = Field("https://api.alphatest1.dev.metapixai.com", alias="API_BASE_URL")
    routing: Routing = Field(Routing.GATEWAY, alias="API_ROUTING")
    web_url: str | None = Field(None, alias="WEB_URL")
    theme: str | None = Field(None, alias="THEME")
    # prod-окружение: запуск только с ALLOW_PRODUCTION=true
    production: bool = Field(False, alias="PRODUCTION")
    allow_production: bool = Field(False, alias="ALLOW_PRODUCTION")
    # окружение смотрит в прод-юзерпул Cognito: тесты user_pool_mutation запрещены
    prod_user_pool: bool = Field(False, alias="PROD_USER_POOL")
    # компания с реальными объектами для object-manager/chartilla (если отличается от TEST_COMPANY_ID)
    objects_company_id: int | None = Field(None, alias="OBJECTS_COMPANY_ID")

    # --- данные окружения из config.yaml ---
    cognito: Cognito = Cognito()
    license_server: LicenseServer = LicenseServer()
    service_provider: ServiceProvider = ServiceProvider()
    dwnx: DwNxAccount = DwNxAccount()
    mailinator_token: SecretStr | None = Field(None, alias="MAILINATOR_TOKEN")
    gitlab_host: str = Field("https://gitlab.dev.metapixai.com/", alias="GITLAB_HOST")
    gitlab_api_token: SecretStr | None = Field(None, alias="GITLAB_API_TOKEN")

    # Переопределение базового URL для конкретного сервиса (нужно для routing=direct).
    auth_manager_url: str | None = Field(None, alias="AUTH_MANAGER_URL")
    object_manager_url: str | None = Field(None, alias="OBJECT_MANAGER_URL")
    layout_manager_url: str | None = Field(None, alias="LAYOUT_MANAGER_URL")

    # --- учётные данные (НЕ коммитить; в CI — masked variables) ---
    test_user_login: str | None = Field(None, alias="TEST_USER_LOGIN")
    test_user_password: SecretStr | None = Field(None, alias="TEST_USER_PASSWORD")
    # Компания, в контексте которой работают тесты. После логина токен не привязан к компании
    # (всё отвечает 403 COMPANY_NOT_SELECTED_ERROR) — фреймворк вызывает PATCH /context/active-company.
    test_company_id: int | None = Field(None, alias="TEST_COMPANY_ID")
    # Альтернатива логину: заранее выданный токен.
    test_access_token: SecretStr | None = Field(None, alias="TEST_ACCESS_TOKEN")
    # Второй пользователь той же компании — для тестов шаринга/прав. Необязателен.
    second_user_login: str | None = Field(None, alias="SECOND_USER_LOGIN")
    second_user_password: SecretStr | None = Field(None, alias="SECOND_USER_PASSWORD")

    # --- поведение HTTP ---
    # (connect, read); REQUEST_TIMEOUT=30 или "10,20"
    request_timeout: Annotated[tuple[float, float], NoDecode] = Field((10.0, 20.0), alias="REQUEST_TIMEOUT")
    verify_ssl: bool = Field(True, alias="VERIFY_SSL")
    retries: int = Field(2, alias="HTTP_RETRIES")
    log_bodies: bool = Field(True, alias="LOG_BODIES")
    max_logged_body: int = Field(4000, alias="MAX_LOGGED_BODY")

    # --- контракт ---
    specs_dir: Path = Field(ROOT_DIR / "specs", alias="SPECS_DIR")
    # strict: отсутствие спеки/схемы ответа — ошибка; иначе — warning и пропуск проверки.
    strict_contract: bool = Field(False, alias="STRICT_CONTRACT")

    # --- данные ---
    test_data_prefix: str = Field("autotest_", alias="TEST_DATA_PREFIX")
    # Разрешить тесты, которые создают неудаляемые сущности или трогают лицензии/камеры.
    allow_destructive: bool = Field(False, alias="ALLOW_DESTRUCTIVE")

    @field_validator("request_timeout", mode="before")
    @classmethod
    def _timeout(cls, v):
        if isinstance(v, (int, float)):
            return (float(v), float(v))
        if isinstance(v, str):
            parts = [float(x) for x in v.replace(";", ",").split(",") if x.strip()]
            return (parts[0], parts[-1])
        return tuple(v)

    @classmethod
    def available_envs(cls) -> list[str]:
        return config_environments()

    def service_url(self, service: str) -> str:
        override = {
            "auth-manager": self.auth_manager_url,
            "object-manager": self.object_manager_url,
            "layout-manager": self.layout_manager_url,
        }.get(service)
        return (override or self.api_base_url).rstrip("/")

    @property
    def has_credentials(self) -> bool:
        return bool(self.test_access_token or (self.test_user_login and self.test_user_password))

    @property
    def has_second_user(self) -> bool:
        return bool(self.second_user_login and self.second_user_password)


def _dotenv_value(key: str) -> str | None:
    path = ROOT_DIR / ".env"
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
