"""Преобразование пути из OpenAPI-спеки в реальный URL.

Пути в клиентах и тестах ВСЕГДА пишутся так, как они записаны в openapi.json
сервиса (например `/public/v4/widgets` или `/object-manager/public/v3/objects/{object_id}`).
Это даёт:
  * однозначную связку тест <-> эндпоинт спеки (покрытие, анализ MR);
  * валидацию ответа по схеме из спеки;
  * переключение gateway/direct без правки тестов.

Правила API gateway (проверено на alphatest1):
  /public/<rest>                  -> /<mount>/<rest>            (auth-manager, layout-manager)
  /<prefix>/public/<rest>         -> /<prefix>/<rest>           (object-manager: object/device/watchlist-manager, chartilla)
  /private/health[/]              -> /<mount>/health[/]
  /<prefix>/private/health[/]     -> /<prefix>/health[/]
  прочие /private/*               -> снаружи недоступны (EndpointNotExposed)
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from config.settings import Routing


class EndpointNotExposed(Exception):
    """Эндпоинт не публикуется через gateway (private API)."""


@dataclass(frozen=True)
class Service:
    name: str  # имя сервиса = имя файла спеки specs/<name>.json
    mount: str  # префикс на gateway для путей вида /public/...

    @property
    def spec_file(self) -> str:
        return f"{self.name}.json"


AUTH_MANAGER = Service(name="auth-manager", mount="auth-manager")
OBJECT_MANAGER = Service(name="object-manager", mount="object-manager")
LAYOUT_MANAGER = Service(name="layout-manager", mount="layout-manager")

SERVICES: dict[str, Service] = {s.name: s for s in (AUTH_MANAGER, OBJECT_MANAGER, LAYOUT_MANAGER)}

_PREFIXED_PUBLIC = re.compile(r"^/(?P<prefix>[\w-]+)/public(?P<rest>/.*)$")
_PREFIXED_HEALTH = re.compile(r"^/(?P<prefix>[\w-]+)/private/health(?P<slash>/?)$")
_ROOT_HEALTH = re.compile(r"^/private/health(?P<slash>/?)$")


def to_gateway_path(service: Service, spec_path: str) -> str:
    if spec_path.startswith("/public/"):
        return f"/{service.mount}{spec_path[len('/public') :]}"
    if m := _ROOT_HEALTH.match(spec_path):
        return f"/{service.mount}/health{m['slash']}"
    if m := _PREFIXED_HEALTH.match(spec_path):
        return f"/{m['prefix']}/health{m['slash']}"
    if m := _PREFIXED_PUBLIC.match(spec_path):
        return f"/{m['prefix']}{m['rest']}"
    raise EndpointNotExposed(f"{service.name}: {spec_path} не публикуется через gateway")


def build_path(service: Service, spec_path: str, routing: Routing, path_params: dict | None = None) -> str:
    path = spec_path.format(**(path_params or {}))
    if routing is Routing.DIRECT:
        return path
    # Подставляем параметры уже после маппинга шаблона, чтобы значения не влияли на правила.
    return to_gateway_path(service, spec_path).format(**(path_params or {}))


def is_exposed(service: Service, spec_path: str, routing: Routing) -> bool:
    if routing is Routing.DIRECT:
        return True
    try:
        to_gateway_path(service, spec_path)
    except EndpointNotExposed:
        return False
    return True
