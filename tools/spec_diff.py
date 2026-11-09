"""Семантический diff двух версий OpenAPI-спеки.

    python -m tools.spec_diff specs/object-manager.json /tmp/new-object-manager.json
    python -m tools.spec_diff specs/object-manager.json --git-ref origin/main   # спека из git vs рабочая копия
    python -m tools.spec_diff OLD NEW --json report.json --md report.md

Находит: новые/удалённые эндпоинты; изменения параметров, тела запроса, кодов ответа;
изменения схем (поля, типы, required, enum) и ВСЕ эндпоинты, которые эти схемы используют
(транзитивно через $ref).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

HTTP_METHODS = ("get", "post", "put", "patch", "delete")
NOISE_KEYS = {"title", "description", "example", "examples"}


# ---------------- helpers ----------------


def operations(spec: dict) -> dict[tuple[str, str], dict]:
    out = {}
    for path, item in (spec.get("paths") or {}).items():
        for method, op in item.items():
            if method in HTTP_METHODS:
                out[(method.upper(), path)] = op
    return out


def strip_noise(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: strip_noise(v) for k, v in node.items() if k not in NOISE_KEYS}
    if isinstance(node, list):
        return [strip_noise(x) for x in node]
    return node


def canon(node: Any) -> str:
    return json.dumps(strip_noise(node), sort_keys=True, ensure_ascii=False)


def direct_refs(node: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            found.add(ref.rsplit("/", 1)[-1])
        for v in node.values():
            found |= direct_refs(v)
    elif isinstance(node, list):
        for v in node:
            found |= direct_refs(v)
    return found


def closure(spec: dict, names: set[str]) -> set[str]:
    schemas = (spec.get("components") or {}).get("schemas") or {}
    seen: set[str] = set()
    stack = list(names)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        stack.extend(direct_refs(schemas.get(name, {})) - seen)
    return seen


def op_schemas(spec: dict, op: dict) -> set[str]:
    return closure(spec, direct_refs(op))


def short_type(schema: dict | None) -> str:
    if not schema:
        return "?"
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            return "|".join(short_type(s) for s in schema[key])
    if schema.get("type") == "array":
        return f"[{short_type(schema.get('items'))}]"
    if "enum" in schema:
        return f"enum{schema['enum']}"
    t = schema.get("type", "any")
    return f"{t}<{schema['format']}>" if "format" in schema else str(t)


# ---------------- schema diff ----------------


def schema_changes(old: dict, new: dict) -> list[str]:
    changes: list[str] = []
    if "enum" in old or "enum" in new:
        o, n = old.get("enum") or [], new.get("enum") or []
        if added := [v for v in n if v not in o]:
            changes.append(f"enum: добавлены значения {added}")
        if removed := [v for v in o if v not in n]:
            changes.append(f"enum: удалены значения {removed} (breaking)")
    op, np_ = old.get("properties") or {}, new.get("properties") or {}
    oreq, nreq = set(old.get("required") or []), set(new.get("required") or [])
    for name in np_.keys() - op.keys():
        changes.append(f"поле +{name}: {short_type(np_[name])}{' (required)' if name in nreq else ''}")
    for name in op.keys() - np_.keys():
        changes.append(f"поле -{name} (breaking для клиентов)")
    for name in op.keys() & np_.keys():
        if canon(op[name]) != canon(np_[name]):
            ot, nt = short_type(op[name]), short_type(np_[name])
            if ot != nt:
                changes.append(f"поле {name}: тип {ot} -> {nt}")
            else:
                d_old, d_new = op[name].get("default"), np_[name].get("default")
                if d_old != d_new:
                    changes.append(f"поле {name}: default {d_old!r} -> {d_new!r}")
                else:
                    changes.append(f"поле {name}: изменены ограничения/вложенная схема")
    for name in (nreq - oreq) & op.keys():
        changes.append(f"поле {name}: стало required (breaking)")
    for name in (oreq - nreq) & np_.keys():
        changes.append(f"поле {name}: стало optional")
    if not changes and canon(old) != canon(new):
        changes.append("изменена структура схемы")
    return changes


# ---------------- operation diff ----------------


def _params(op: dict) -> dict[tuple[str, str], dict]:
    return {(p.get("in"), p.get("name")): p for p in op.get("parameters") or []}


def _status_codes(op: dict) -> set[str]:
    return {k.strip() for k in (op.get("responses") or {})}


def op_changes(old_spec: dict, new_spec: dict, old: dict, new: dict, changed_schemas: set[str]) -> list[str]:
    changes: list[str] = []
    op_, np_ = _params(old), _params(new)
    for key in np_.keys() - op_.keys():
        p = np_[key]
        changes.append(f"параметр +{key[0]}:{key[1]} {short_type(p.get('schema'))}{' (required)' if p.get('required') else ''}")
    for key in op_.keys() - np_.keys():
        changes.append(f"параметр -{key[0]}:{key[1]}")
    for key in op_.keys() & np_.keys():
        o, n = op_[key], np_[key]
        if bool(o.get("required")) != bool(n.get("required")):
            changes.append(f"параметр {key[1]}: required {bool(o.get('required'))} -> {bool(n.get('required'))}")
        if canon(o.get("schema")) != canon(n.get("schema")):
            changes.append(f"параметр {key[1]}: схема {short_type(o.get('schema'))} -> {short_type(n.get('schema'))}")
    ob, nb = old.get("requestBody"), new.get("requestBody")
    if bool(ob) != bool(nb):
        changes.append("тело запроса " + ("добавлено" if nb else "удалено"))
    elif ob and nb and canon(ob) != canon(nb) and not (direct_refs(ob) & changed_schemas):
        changes.append("тело запроса изменено")
    oc, nc = _status_codes(old), _status_codes(new)
    if nc - oc:
        changes.append(f"новые коды ответа {sorted(nc - oc)}")
    if oc - nc:
        changes.append(f"удалены коды ответа {sorted(oc - nc)}")
    used = op_schemas(new_spec, new) & changed_schemas
    for name in sorted(used):
        changes.append(f"использует изменённую схему {name}")
    return changes


def diff_specs(old_spec: dict, new_spec: dict) -> dict:
    old_ops, new_ops = operations(old_spec), operations(new_spec)
    old_schemas = (old_spec.get("components") or {}).get("schemas") or {}
    new_schemas = (new_spec.get("components") or {}).get("schemas") or {}

    changed_schemas: dict[str, list[str]] = {}
    for name in old_schemas.keys() & new_schemas.keys():
        if canon(old_schemas[name]) != canon(new_schemas[name]):
            changed_schemas[name] = schema_changes(old_schemas[name], new_schemas[name])
    added_schemas = sorted(new_schemas.keys() - old_schemas.keys())
    removed_schemas = sorted(old_schemas.keys() - new_schemas.keys())

    changed_set = set(changed_schemas)
    changed_endpoints = []
    for key in sorted(old_ops.keys() & new_ops.keys()):
        changes = op_changes(old_spec, new_spec, old_ops[key], new_ops[key], changed_set)
        if changes:
            changed_endpoints.append({"method": key[0], "path": key[1], "changes": changes})

    schema_usage = {name: [f"{m} {p}" for (m, p), op in sorted(new_ops.items()) if name in op_schemas(new_spec, op)] for name in changed_schemas}

    def describe(key, op):
        return {"method": key[0], "path": key[1], "operation_id": op.get("operationId"), "tags": op.get("tags", [])}

    report = {
        "added_endpoints": [describe(k, new_ops[k]) for k in sorted(new_ops.keys() - old_ops.keys())],
        "removed_endpoints": [describe(k, old_ops[k]) for k in sorted(old_ops.keys() - new_ops.keys())],
        "changed_endpoints": changed_endpoints,
        "changed_schemas": [{"name": n, "changes": c, "used_by": schema_usage[n]} for n, c in sorted(changed_schemas.items())],
        "added_schemas": added_schemas,
        "removed_schemas": removed_schemas,
    }
    report["has_changes"] = any(report[k] for k in ("added_endpoints", "removed_endpoints", "changed_endpoints", "changed_schemas"))
    return report


def render_markdown(report: dict) -> str:
    lines: list[str] = []
    if report["added_endpoints"]:
        lines.append("### Новые эндпоинты")
        lines += [f"- `{e['method']} {e['path']}`" for e in report["added_endpoints"]]
    if report["removed_endpoints"]:
        lines.append("### Удалённые эндпоинты (breaking)")
        lines += [f"- `{e['method']} {e['path']}`" for e in report["removed_endpoints"]]
    if report["changed_endpoints"]:
        lines.append("### Изменённые эндпоинты")
        for e in report["changed_endpoints"]:
            lines.append(f"- `{e['method']} {e['path']}`")
            lines += [f"  - {c}" for c in e["changes"]]
    if report["changed_schemas"]:
        lines.append("### Изменённые схемы")
        for s in report["changed_schemas"]:
            lines.append(f"- `{s['name']}` (используется в {len(s['used_by'])} эндпоинтах)")
            lines += [f"  - {c}" for c in s["changes"]]
    return "\n".join(lines) if lines else "_изменений нет_"


def _load(path_or_ref: str, git_ref: str | None = None) -> dict:
    if git_ref:
        out = subprocess.run(["git", "show", f"{git_ref}:{path_or_ref}"], capture_output=True, text=True, check=False)
        if out.returncode != 0:
            return {"paths": {}, "components": {}}
        return json.loads(out.stdout)
    return json.loads(Path(path_or_ref).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("old")
    parser.add_argument("new", nargs="?")
    parser.add_argument("--git-ref", help="взять OLD из git (git show REF:OLD), NEW = рабочая копия OLD")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--md", type=Path)
    args = parser.parse_args()

    if args.git_ref:
        old, new = _load(args.old, args.git_ref), _load(args.new or args.old)
    else:
        if not args.new:
            parser.error("нужен NEW или --git-ref")
        old, new = _load(args.old), _load(args.new)
    report = diff_specs(old, new)
    md = render_markdown(report)
    if args.json:
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.md:
        args.md.write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
