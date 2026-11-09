"""Покрытие эндпоинтов спеки автотестами (по маркеру @endpoint).

    python -m tools.coverage                     # таблица по всем сервисам
    python -m tools.coverage --service layout-manager --uncovered
    python -m tools.coverage --json reports/coverage.json --fail-under 80

Эндпоинт считается покрытым, если есть хотя бы один тест с @endpoint(service, METHOD, path).
Осознанно непокрытые эндпоинты (опасные/служебные) перечисляются в tools/coverage_ignore.yaml.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from framework.openapi import iter_operations, load_spec  # noqa: E402
from framework.routing import SERVICES  # noqa: E402

IGNORE_FILE = ROOT / "tools" / "coverage_ignore.yaml"


class _Collector:
    def __init__(self) -> None:
        self.map: dict[tuple[str, str, str], list[str]] = defaultdict(list)

    def pytest_collection_finish(self, session):
        for item in session.items:
            for m in item.iter_markers("api"):
                self.map[(m.kwargs["service"], m.kwargs["method"], m.kwargs["path"])].append(item.nodeid)


def collect_test_map(test_paths: list[str] | None = None) -> dict[tuple[str, str, str], list[str]]:
    collector = _Collector()
    args = ["--collect-only", "-q", "-p", "no:cacheprovider", "-o", "log_cli=false", *(test_paths or [str(ROOT / "tests")])]
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        pytest.main(args, plugins=[collector])
    return dict(collector.map)


def load_ignore() -> dict[tuple[str, str, str], str]:
    if not IGNORE_FILE.exists():
        return {}
    data = yaml.safe_load(IGNORE_FILE.read_text(encoding="utf-8")) or {}
    out = {}
    for service, entries in data.items():
        for entry in entries or []:
            method, path = entry["endpoint"].split(" ", 1)
            out[(service, method.upper(), path)] = entry.get("reason", "")
    return out


def build_report(services: list[str]) -> dict:
    test_map = collect_test_map()
    ignore = load_ignore()
    report: dict = {"services": {}, "unknown_markers": []}
    known: set[tuple[str, str, str]] = set()
    for service in services:
        spec = load_spec(service)
        if spec is None:
            report["services"][service] = {"error": f"нет specs/{service}.json — запустите python -m tools.fetch_specs"}
            continue
        rows = []
        for method, path, op in iter_operations(spec):
            key = (service, method, path)
            known.add(key)
            tests = test_map.get(key, [])
            status = "covered" if tests else ("ignored" if key in ignore else "uncovered")
            rows.append(
                {
                    "method": method,
                    "path": path,
                    "operation_id": op.get("operationId"),
                    "status": status,
                    "tests": tests,
                    "ignore_reason": ignore.get(key),
                }
            )
        total = len([r for r in rows if r["status"] != "ignored"])
        covered = len([r for r in rows if r["status"] == "covered"])
        report["services"][service] = {
            "endpoints": rows,
            "total": total,
            "covered": covered,
            "percent": round(100 * covered / total, 1) if total else 100.0,
        }
    # маркеры на эндпоинты, которых нет в спеке — обычно опечатка или удалённый эндпоинт
    report["unknown_markers"] = [
        {"service": s, "method": m, "path": p, "tests": t}
        for (s, m, p), t in test_map.items()
        if s in services and "error" not in report["services"].get(s, {}) and (s, m, p) not in known
    ]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--service", choices=sorted(SERVICES), action="append")
    parser.add_argument("--uncovered", action="store_true", help="показать только непокрытые")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--fail-under", type=float, default=0.0)
    args = parser.parse_args()

    report = build_report(args.service or sorted(SERVICES))
    worst = 100.0
    for service, data in report["services"].items():
        if "error" in data:
            print(f"\n## {service}: {data['error']}")
            continue
        worst = min(worst, data["percent"])
        print(f"\n## {service}: {data['covered']}/{data['total']} ({data['percent']}%)")
        for row in data["endpoints"]:
            if args.uncovered and row["status"] != "uncovered":
                continue
            mark = {"covered": "+", "uncovered": "-", "ignored": "~"}[row["status"]]
            extra = f"  ({len(row['tests'])} tests)" if row["tests"] else (f"  [ignore: {row['ignore_reason']}]" if row["ignore_reason"] else "")
            print(f"  {mark} {row['method']:6} {row['path']}{extra}")
    if report["unknown_markers"]:
        print("\n## Маркеры на эндпоинты, которых нет в спеке:")
        for m in report["unknown_markers"]:
            print(f"  ! {m['service']} {m['method']} {m['path']} <- {m['tests'][0]}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return 1 if worst < args.fail_under else 0


if __name__ == "__main__":
    sys.exit(main())
