from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from config.settings import Settings
from framework.http_client import ApiClient
from framework.routing import Service


class ApiModel(BaseModel):
    """Базовая модель ответа: лишние поля разрешены (контракт проверяет assert_contract)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)


class ServiceClient(ApiClient):
    SERVICE: Service

    def __init__(self, token: str | None = None, settings: Settings | None = None):
        super().__init__(self.SERVICE, token=token, settings=settings)


def drop_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}
