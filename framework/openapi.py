"""Работа с OpenAPI-спеками: поиск операций и контрактная валидация ответов.

Спеки лежат в specs/<service>.json и обновляются `python -m tools.fetch_specs`.
"""

from __future__ import annotations

import copy
import json
import logging
import warnings
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator

from config.settings import get_settings

log = logging.getLogger("api.contract")

HTTP_METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


class ContractError(AssertionError):
    pass


@lru_cache
def load_spec(service: str) -> dict | None:
    path = get_settings().specs_dir / f"{service}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def iter_operations(spec: dict) -> Iterator[tuple[str, str, dict]]:
    for path, item in spec.get("paths", {}).items():
        for method, op in item.items():
            if method in HTTP_METHODS:
                yield method.upper(), path, op


def find_operation(spec: dict, method: str, spec_path: str) -> dict | None:
    return spec.get("paths", {}).get(spec_path, {}).get(method.lower())


def has_operation(service: str, method: str, spec_path: str) -> bool:
    spec = load_spec(service)
    return spec is not None and find_operation(spec, method, spec_path) is not None


def _response_entry(op: dict, status: int) -> dict | None:
    # FastAPI-спеки metapix содержат ключи с хвостовыми пробелами ("403 ", "403  ") —
    # так сервисы описывают несколько вариантов ошибки с одним кодом.
    responses = op.get("responses", {})
    for key, value in responses.items():
        if key.strip() == str(status):
            return value
    return responses.get(f"{str(status)[0]}XX") or responses.get("default")


def response_schema(op: dict, status: int) -> dict | None:
    entry = _response_entry(op, status)
    if not entry:
        return None
    content = entry.get("content") or {}
    media = content.get("application/json") or next(iter(content.values()), None)
    return (media or {}).get("schema")


def documented_statuses(op: dict) -> set[int]:
    return {int(k.strip()) for k in op.get("responses", {}) if k.strip().isdigit()}


# ---------------------------------------------------------------------------
# Нормализация схем.
# Бэкенд на pydantic v1: Optional-поля в схеме НЕ помечены nullable, но реально
# приходят как null. Поэтому необязательные (не из required) свойства разрешаем как null.
# ---------------------------------------------------------------------------


def _allow_null(schema: Any) -> dict:
    return {"anyOf": [schema, {"type": "null"}]}


def _normalize(node: Any) -> Any:
    if isinstance(node, list):
        return [_normalize(x) for x in node]
    if not isinstance(node, dict):
        return node
    node = {k: _normalize(v) for k, v in node.items()}
    if node.pop("nullable", False):
        node = _allow_null(node)
        return node
    props = node.get("properties")
    if isinstance(props, dict):
        required = set(node.get("required", []))
        node["properties"] = {name: (sub if name in required else _allow_null(sub)) for name, sub in props.items()}
    return node


@lru_cache
def _normalized_components(service: str) -> dict:
    spec = load_spec(service) or {}
    return _normalize(copy.deepcopy(spec.get("components", {})))


def validate_response(service: str, method: str, spec_path: str, status: int, body: Any) -> None:
    """Проверить тело ответа по схеме из спеки. Бросает ContractError."""
    settings = get_settings()
    spec = load_spec(service)

    def _soft(msg: str) -> None:
        if settings.strict_contract:
            raise ContractError(msg)
        warnings.warn(msg, stacklevel=3)

    if spec is None:
        return _soft(f"Нет спеки specs/{service}.json — контракт не проверен. Запустите tools.fetch_specs")
    op = find_operation(spec, method, spec_path)
    if op is None:
        raise ContractError(f"{method} {spec_path} отсутствует в спеке {service}")
    if status not in documented_statuses(op) and status != 422:
        raise ContractError(f"{method} {spec_path}: статус {status} не задокументирован (есть {sorted(documented_statuses(op))})")
    schema = response_schema(op, status)
    if schema is None:
        return None
    full = {**_normalize(copy.deepcopy(schema)), "components": _normalized_components(service)}
    errors = sorted(Draft202012Validator(full).iter_errors(body), key=lambda e: list(e.absolute_path))
    if errors:
        details = "\n".join(f"  - {'/'.join(map(str, e.absolute_path)) or '<root>'}: {e.message}" for e in errors[:15])
        raise ContractError(f"{method} {spec_path} -> {status}: ответ не соответствует схеме:\n{details}")
    return None
