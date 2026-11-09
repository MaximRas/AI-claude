"""Анализ влияния MR бэкенд-сервиса (FastAPI) на API: какие эндпоинты затронуты,
какие тесты запускать и где тестов не хватает.

Детерминированная часть для агента api-test-impact-analyzer. Агент читает этот отчёт,
затем сам смотрит diff и решает, что проверять/дописывать.

Примеры:
    # в CI сервиса (репозиторий сервиса в ./service, MR в $CI_MERGE_REQUEST_DIFF_BASE_SHA)
    python -m tools.mr_impact --repo ../object-manager --base origin/dev --service object-manager \
        --json reports/impact.json --md reports/impact.md

    # из готового diff-файла (+ исходники в --repo для разбора AST)
    python -m tools.mr_impact --diff mr.diff --repo ../object-manager --service object-manager

    # если CI смог сгенерировать спеку из кода MR — добавится семантический diff спеки
    python -m tools.mr_impact --repo ../object-manager --base origin/dev --new-spec /tmp/openapi.json

Как работает:
  1. Парсит unified diff -> изменённые строки по файлам.
  2. AST роутеров (`<router> = APIRouter(prefix=...)`, `@<router>.get("/path")`) ->
     какие route-функции изменены; новые/удалённые декораторы -> новые/удалённые эндпоинты.
  3. Изменённые классы (pydantic-схемы, Enum) -> по спеке находит все эндпоинты, где эта схема
     участвует (транзитивно через $ref).
  4. Изменённые функции в остальных модулях (queries, core, db) -> какие route-функции их вызывают
     (по имени, до 3 уровней вложенности).
  5. По маркерам @endpoint находит существующие тесты и непокрытые эндпоинты.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from framework.openapi import iter_operations, load_spec  # noqa: E402
from tools.spec_diff import closure, diff_specs, direct_refs, render_markdown  # noqa: E402

ROUTE_METHODS = {"get", "post", "put", "patch", "delete", "websocket"}
HUNK_RE = re.compile(r"^@@ -(?P<os>\d+)(?:,(?P<oc>\d+))? \+(?P<ns>\d+)(?:,(?P<nc>\d+))? @@")


# ---------------- diff parsing ----------------


@dataclass
class FileDiff:
    path: str
    old_path: str | None = None
    added: set[int] = field(default_factory=set)  # номера строк в новой версии
    removed: set[int] = field(default_factory=set)  # номера строк в старой версии
    added_text: list[str] = field(default_factory=list)
    removed_text: list[str] = field(default_factory=list)
    is_new: bool = False
    is_deleted: bool = False


def parse_unified_diff(text: str) -> dict[str, FileDiff]:
    files: dict[str, FileDiff] = {}
    current: FileDiff | None = None
    old_line = new_line = 0
    old_path = None
    for line in text.splitlines():
        if line.startswith("diff --git"):
            current = None
            continue
        if line.startswith("--- "):
            old_path = None if line.endswith("/dev/null") else line[4:].removeprefix("a/")
            continue
        if line.startswith("+++ "):
            new_path = None if line.endswith("/dev/null") else line[4:].removeprefix("b/")
            path = new_path or old_path
            current = files.setdefault(path, FileDiff(path=path, old_path=old_path))
            current.is_new = old_path is None
            current.is_deleted = new_path is None
            continue
        if current is None:
            continue
        if m := HUNK_RE.match(line):
            old_line, new_line = int(m["os"]), int(m["ns"])
            continue
        if line.startswith("+") and not line.startswith("+++"):
            current.added.add(new_line)
            current.added_text.append(line[1:])
            new_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            current.removed.add(old_line)
            current.removed_text.append(line[1:])
            old_line += 1
        elif line.startswith("\\"):
            continue
        else:
            old_line += 1
            new_line += 1
    return files


# ---------------- AST ----------------


@dataclass
class Route:
    method: str
    path: str  # полный путь = prefix + path (совпадает с путём в спеке)
    func: str
    file: str
    start: int  # первая строка декоратора
    end: int


def _str_value(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):  # f-строки — берём только константные части
        return "".join(v.value for v in node.values if isinstance(v, ast.Constant))
    return None


def _router_prefixes(tree: ast.Module) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            fn = node.value.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name == "APIRouter":
                prefix = next((_str_value(k.value) for k in node.value.keywords if k.arg == "prefix"), "") or ""
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        prefixes[target.id] = prefix
    return prefixes


def extract_routes(source: str, file: str) -> list[Route]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    prefixes = _router_prefixes(tree)
    routes = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                continue
            method = dec.func.attr
            router = dec.func.value
            if method not in ROUTE_METHODS or not isinstance(router, ast.Name):
                continue
            sub = _str_value(dec.args[0]) if dec.args else next((_str_value(k.value) for k in dec.keywords if k.arg == "path"), "")
            routes.append(
                Route(
                    method=method.upper(),
                    path=prefixes.get(router.id, "") + (sub or ""),
                    func=node.name,
                    file=file,
                    start=min(d.lineno for d in node.decorator_list),
                    end=node.end_lineno or node.lineno,
                )
            )
    return routes


@dataclass
class Definition:
    name: str
    kind: str  # class | function
    start: int
    end: int
    bases: list[str] = field(default_factory=list)


def extract_definitions(source: str) -> list[Definition]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = [b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "") for b in node.bases]
            out.append(Definition(node.name, "class", node.lineno, node.end_lineno or node.lineno, bases))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(Definition(node.name, "function", node.lineno, node.end_lineno or node.lineno))
    return out


def called_names(source: str) -> dict[str, set[str]]:
    """func_name -> множество имён, которые она вызывает/упоминает (Name и Attribute)."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {}
    out: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names = set()
            for sub in ast.walk(node):
                if isinstance(sub, ast.Name):
                    names.add(sub.id)
                elif isinstance(sub, ast.Attribute):
                    names.add(sub.attr)
            out[node.name] = names
    return out


def _overlaps(lines: set[int], start: int, end: int) -> bool:
    return any(start <= n <= end for n in lines)


# ---------------- git ----------------


def git(repo: Path, *args: str) -> str:
    res = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {res.stderr.strip()}")
    return res.stdout


def read_new(repo: Path | None, path: str) -> str | None:
    if repo is None:
        return None
    p = repo / path
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else None


def read_old(repo: Path | None, base: str | None, path: str) -> str | None:
    if repo is None or base is None:
        return None
    try:
        return git(repo, "show", f"{base}:{path}")
    except RuntimeError:
        return None


def detect_service(repo: Path | None) -> str | None:
    if repo is None:
        return None
    for main in repo.glob("*/main.py"):
        m = re.search(r'openapi_url\s*=\s*"/([\w-]+)/openapi\.json"', main.read_text(encoding="utf-8", errors="ignore"))
        if m:
            return m.group(1)
    return None


# ---------------- analysis ----------------


def schema_component_names(spec: dict, class_name: str) -> set[str]:
    """Компоненты спеки, соответствующие python-классу (учитывая namespaced: pkg__mod__Class)."""
    names = (spec.get("components") or {}).get("schemas") or {}
    return {n for n in names if n == class_name or n.endswith(f"__{class_name}") or n.startswith(f"{class_name}_")}


def endpoints_using(spec: dict, components: set[str]) -> set[tuple[str, str]]:
    out = set()
    for method, path, op in iter_operations(spec):
        if closure(spec, direct_refs(op)) & components:
            out.add((method, path))
    return out


def analyze(
    diff_text: str,
    repo: Path | None,
    base: str | None,
    service: str,
    new_spec: dict | None = None,
    test_map: dict | None = None,
) -> dict:
    files = parse_unified_diff(diff_text)
    spec = load_spec(service) or {"paths": {}, "components": {}}
    spec_ops = {(m, p) for m, p, _ in iter_operations(spec)}

    affected: dict[tuple[str, str], set[str]] = defaultdict(set)
    new_endpoints: list[dict] = []
    removed_endpoints: list[dict] = []
    changed_classes: dict[str, str] = {}
    changed_functions: dict[str, str] = {}
    unmapped: list[str] = []
    all_routes: list[Route] = []
    route_calls: dict[tuple[str, str], set[str]] = {}
    funcs_calls: dict[str, set[str]] = {}

    # Индекс всех роутов и call-графа по исходникам сервиса (новая версия)
    if repo is not None:
        for py in repo.rglob("*.py"):
            rel = py.relative_to(repo).as_posix()
            if any(part in {"tests", "alembic", "deps", ".venv", "venv"} for part in py.relative_to(repo).parts):
                continue
            src = py.read_text(encoding="utf-8", errors="replace")
            calls = called_names(src)
            for fname, names in calls.items():
                funcs_calls.setdefault(fname, set()).update(names)
            for r in extract_routes(src, rel):
                all_routes.append(r)
                route_calls[(r.method, r.path)] = calls.get(r.func, set())

    for path, fd in files.items():
        if not path.endswith(".py"):
            if path.endswith((".json", ".yaml", ".yml", ".sql")) and "/resources/" in f"/{path}":
                unmapped.append(f"{path} (ресурс — может влиять на ответы, проверьте вручную)")
            elif not path.endswith((".md", ".lock", ".toml", ".cfg", ".ini", ".txt")) and not path.startswith(("tests/", ".")):
                unmapped.append(path)
            continue
        if path.startswith("tests/") or "/tests/" in path:
            continue
        if "alembic/versions" in path:
            unmapped.append(f"{path} (миграция БД — проверьте эндпоинты, читающие изменённые таблицы)")
            continue

        new_src = None if fd.is_deleted else read_new(repo, path)
        old_src = None if fd.is_new else read_old(repo, base, fd.old_path or path)

        new_routes = extract_routes(new_src, path) if new_src else []
        old_routes = extract_routes(old_src, path) if old_src else []
        new_keys = {(r.method, r.path) for r in new_routes}
        old_keys = {(r.method, r.path) for r in old_routes}

        if old_src is not None or fd.is_new:
            for r in new_routes:
                if (r.method, r.path) not in old_keys:
                    new_endpoints.append({"method": r.method, "path": r.path, "func": r.func, "file": path, "in_spec": (r.method, r.path) in spec_ops})
            for r in old_routes:
                if (r.method, r.path) not in new_keys:
                    removed_endpoints.append({"method": r.method, "path": r.path, "func": r.func, "file": path})
        elif new_src is not None:
            # нет base: новые роуты определяем по добавленным строкам декоратора
            for r in new_routes:
                if r.start in fd.added and (r.method, r.path) not in spec_ops:
                    new_endpoints.append({"method": r.method, "path": r.path, "func": r.func, "file": path, "in_spec": False})

        for r in new_routes:
            if (r.method, r.path) in old_keys or old_src is None:
                if _overlaps(fd.added, r.start, r.end):
                    affected[(r.method, r.path)].add(f"изменён обработчик {r.func} ({path})")
        for r in old_routes:
            if (r.method, r.path) in new_keys and _overlaps(fd.removed, r.start, r.end):
                affected[(r.method, r.path)].add(f"изменён обработчик {r.func} ({path})")

        route_funcs = {r.func for r in new_routes}
        for src, lines in ((new_src, fd.added), (old_src, fd.removed)):
            if not src:
                continue
            for d in extract_definitions(src):
                if not _overlaps(lines, d.start, d.end):
                    continue
                if d.kind == "class":
                    changed_classes[d.name] = path
                elif d.name not in route_funcs:
                    changed_functions[d.name] = path

        if new_src is None and old_src is None:
            unmapped.append(f"{path} (нет исходников для AST: передайте --repo/--base)")

    # Схемы -> эндпоинты через спеку
    schema_hits: dict[str, list[str]] = {}
    for cls, file in changed_classes.items():
        comps = schema_component_names(spec, cls)
        if not comps:
            # класс не попал в спеку напрямую — ищем в коде роутов по имени
            for key, names in route_calls.items():
                if cls in names:
                    affected[key].add(f"использует класс {cls} ({file})")
            continue
        eps = endpoints_using(spec, comps)
        schema_hits[cls] = sorted(f"{m} {p}" for m, p in eps)
        for key in eps:
            affected[key].add(f"схема {cls} изменена ({file})")

    # Функции -> роуты через call-граф (до 3 уровней)
    for fname, file in changed_functions.items():
        frontier, seen = {fname}, {fname}
        for depth in range(3):
            for key, names in route_calls.items():
                if names & frontier:
                    affected[key].add(f"вызывает изменённую {fname} ({file})" + (f", глубина {depth + 1}" if depth else ""))
            callers = {f for f, names in funcs_calls.items() if names & frontier} - seen
            seen |= callers
            frontier = callers
            if not frontier:
                break

    new_keys_all = {(e["method"], e["path"]) for e in new_endpoints}
    for key in new_keys_all:
        affected.pop(key, None)

    spec_report = diff_specs(spec, new_spec) if new_spec else None
    if spec_report:
        for e in spec_report["changed_endpoints"]:
            affected[(e["method"], e["path"])].update(f"spec: {c}" for c in e["changes"])
        for e in spec_report["added_endpoints"]:
            if (e["method"], e["path"]) not in new_keys_all:
                new_endpoints.append({**e, "file": None, "in_spec": False})

    # Тесты
    if test_map is None:
        from tools.coverage import collect_test_map

        test_map = collect_test_map()
    tests_for = {(m, p): t for (s, m, p), t in test_map.items() if s == service}

    changed = []
    for (method, path), reasons in sorted(affected.items()):
        tests = tests_for.get((method, path), [])
        changed.append({"method": method, "path": path, "reasons": sorted(reasons), "tests": tests, "covered": bool(tests)})

    for e in new_endpoints:
        e["tests"] = tests_for.get((e["method"], e["path"]), [])

    impacted_tests = sorted({t for e in changed for t in e["tests"]} | {t for e in new_endpoints for t in e["tests"]})
    return {
        "service": service,
        "base": base,
        "files_changed": sorted(files),
        "new_endpoints": new_endpoints,
        "removed_endpoints": removed_endpoints,
        "changed_endpoints": changed,
        "changed_schemas": schema_hits,
        "changed_functions": changed_functions,
        "uncovered_changed_endpoints": [f"{e['method']} {e['path']}" for e in changed if not e["covered"]],
        "impacted_tests": impacted_tests,
        "unmapped_changes": unmapped,
        "spec_diff": spec_report,
        "pytest_command": _pytest_cmd(impacted_tests),
    }


def _pytest_cmd(tests: list[str]) -> str | None:
    if not tests:
        return None
    files = sorted({t.split("::")[0] for t in tests})
    return "pytest " + " ".join(files) if len(tests) > 40 else "pytest " + " ".join(f'"{t}"' for t in tests)


def render(report: dict) -> str:
    out = [f"## API impact: {report['service']}"]
    if report["new_endpoints"]:
        out.append("\n### Новые эндпоинты — нужны новые тесты")
        for e in report["new_endpoints"]:
            status = "есть тесты" if e.get("tests") else "**тестов нет**"
            out.append(f"- `{e['method']} {e['path']}` ({e.get('file') or 'spec'}) — {status}")
    if report["removed_endpoints"]:
        out.append("\n### Удалённые эндпоинты — удалить/обновить тесты")
        out += [f"- `{e['method']} {e['path']}` ({e['file']})" for e in report["removed_endpoints"]]
    if report["changed_endpoints"]:
        out.append("\n### Затронутые эндпоинты")
        for e in report["changed_endpoints"]:
            cov = f"тестов: {len(e['tests'])}" if e["tests"] else "**не покрыт**"
            out.append(f"- `{e['method']} {e['path']}` — {cov}")
            out += [f"  - {r}" for r in e["reasons"][:6]]
    if report["unmapped_changes"]:
        out.append("\n### Изменения без явной привязки к эндпоинтам")
        out += [f"- {u}" for u in report["unmapped_changes"]]
    if report["spec_diff"] and report["spec_diff"]["has_changes"]:
        out.append("\n### Diff спеки\n" + render_markdown(report["spec_diff"]))
    if report["pytest_command"]:
        out.append(f"\n### Запуск\n```\n{report['pytest_command']}\n```")
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--diff", type=Path, help="unified diff (git diff base...head); '-' = stdin")
    parser.add_argument("--repo", type=Path, help="checkout сервиса на коммите MR (для AST)")
    parser.add_argument("--base", help="git-ref базы MR (например origin/dev); если без --diff — diff посчитается сам")
    parser.add_argument("--service", help="имя сервиса = specs/<name>.json (по умолчанию — из main.py openapi_url)")
    parser.add_argument("--new-spec", type=Path, help="openapi.json, сгенерированный из кода MR")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--md", type=Path)
    args = parser.parse_args()

    if args.diff:
        diff_text = sys.stdin.read() if str(args.diff) == "-" else args.diff.read_text(encoding="utf-8")
    elif args.repo and args.base:
        diff_text = git(args.repo, "diff", "--unified=3", f"{args.base}...HEAD")
    else:
        parser.error("нужен --diff или --repo + --base")

    service = args.service or detect_service(args.repo)
    if not service:
        parser.error("не удалось определить сервис — передайте --service")
    new_spec = json.loads(args.new_spec.read_text(encoding="utf-8")) if args.new_spec else None

    report = analyze(diff_text, args.repo.resolve() if args.repo else None, args.base, service, new_spec)
    md = render(report)
    for target, content in ((args.json, json.dumps(report, indent=2, ensure_ascii=False)), (args.md, md)):
        if target:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
