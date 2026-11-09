"""Снимок лейаутов/виджетов/шаринга ДО релиза и сверка ПОСЛЕ — проверка миграций layout-manager
на реальных данных стенда («что было расшарено — так и осталось, нерасшаренное — закрыто,
расположение и размеры виджетов не съехали»).

Только чтение. Обходит компании тестового пользователя (контекст компании — per-token, поэтому
на каждую компанию берётся отдельный токен).

    # до деплоя релиза на стенд
    python -m tools.layout_baseline snapshot --out reports/layout_baseline_staging.json
    # после деплоя
    python -m tools.layout_baseline compare reports/layout_baseline_staging.json --md reports/layout_compare.md
    # или тестом (упадёт при расхождениях):
    LAYOUT_BASELINE_FILE=reports/layout_baseline_staging.json pytest -m release_check

Опции: --companies 1,8375 (по умолчанию — все доступные), --max-per-company 1000.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import get_settings  # noqa: E402
from framework.auth import AuthError, TokenProvider  # noqa: E402
from services.auth_manager.client import AuthManagerClient  # noqa: E402
from services.layout_manager.client import LayoutManagerClient  # noqa: E402

PAGE = 100
# Поля, которые сравниваем (legacy-поля виджетов намеренно не сравниваются — их убрали из API)
LAYOUT_FIELDS = ("name", "ordering", "state", "is_shared", "access_role", "user_id")
WIDGET_FIELDS = ("name", "type", "state", "is_shared", "access_role", "parent_layout_id", "user_id")


def _all_pages(fetch) -> list[dict]:
    items, offset = [], 0
    while True:
        body = fetch(offset).assert_status(200).json()
        items += body["items"]
        offset += PAGE
        if offset >= body["pagination"]["amount"] or not body["items"]:
            return items


def _access(api: LayoutManagerClient, kind: str, entity_id: str) -> list[list]:
    resp = api.get_access(kind, entity_id)
    if resp.status_code != 200:  # не владелец — список доступов не виден
        return [["<no-access-list>", resp.status_code]]
    return sorted([e["scope"], e["role"], e.get("user_id")] for e in resp.json())


def snapshot_company(api: LayoutManagerClient, max_items: int) -> dict[str, Any]:
    layouts = _all_pages(lambda off: api.list_layouts(pgoffset=off, pgsize=PAGE, scope="all"))[:max_items]
    widgets = _all_pages(lambda off: api.list_widgets(pgoffset=off, pgsize=PAGE, scope="all"))[:max_items]
    snap: dict[str, Any] = {"layouts": {}, "widgets": {}, "errors": []}
    for lay in layouts:
        full = api.get_layout(lay["id"])
        if full.status_code != 200:
            snap["errors"].append(f"GET layout {lay['id']} -> {full.status_code}")
            continue
        body = full.json()
        entry = {k: body.get(k) for k in LAYOUT_FIELDS}
        entry["grid"] = sorted([c["id"], c["x"], c["y"], c["w"], c["h"]] for c in body.get("grid", []))
        entry["access"] = _access(api, "layouts", lay["id"]) if body.get("access_role") == "owner" else None
        snap["layouts"][lay["id"]] = entry
    for w in widgets:
        full = api.get_widget(w["id"])
        if full.status_code != 200:
            snap["errors"].append(f"GET widget {w['id']} -> {full.status_code}")
            continue
        body = full.json()
        entry = {k: body.get(k) for k in WIDGET_FIELDS}
        standalone_owner = body.get("access_role") == "owner" and not body.get("parent_layout_id")
        entry["access"] = _access(api, "widgets", w["id"]) if standalone_owner else None
        snap["widgets"][w["id"]] = entry
    return snap


def take_snapshot(company_ids: list[int] | None = None, max_items: int = 1000) -> dict[str, Any]:
    s = get_settings()
    if not (s.test_user_login and s.test_user_password):
        raise SystemExit("Нужны TEST_USER_LOGIN/TEST_USER_PASSWORD")
    tp = TokenProvider(s)
    login = lambda: tp.login(s.test_user_login, s.test_user_password.get_secret_value()).access_token  # noqa: E731
    if not company_ids:
        company_ids = [c["id"] for c in AuthManagerClient(login()).available_companies().assert_status(200).json()]
    result: dict[str, Any] = {
        "env": s.env_name,
        "base_url": s.api_base_url,
        "taken_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "companies": {},
    }
    for cid in company_ids:
        token = login()
        try:
            tp.select_company(token, cid)
        except AuthError as exc:  # например, компания помечена на удаление — не участвует в сверке
            print(f"company {cid}: пропущена ({exc})", file=sys.stderr)
            result.setdefault("skipped", {})[str(cid)] = str(exc)[:200]
            continue
        result["companies"][str(cid)] = snapshot_company(LayoutManagerClient(token), max_items)
        c = result["companies"][str(cid)]
        print(f"company {cid}: layouts={len(c['layouts'])} widgets={len(c['widgets'])} errors={len(c['errors'])}", file=sys.stderr)
    return result


def compare(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """Список расхождений. Новые сущности (созданные после снимка) не считаются расхождением."""
    problems: list[str] = []
    for cid, b in before["companies"].items():
        a = after["companies"].get(cid)
        if a is None:
            problems.append(f"[{cid}] компания отсутствует в новом снимке")
            continue
        problems += [f"[{cid}] {e}" for e in a.get("errors", [])]
        for kind in ("layouts", "widgets"):
            for eid, old in b[kind].items():
                new = a[kind].get(eid)
                if new is None:
                    problems.append(f"[{cid}] {kind[:-1]} {eid} ({old.get('name')!r}) пропал")
                    continue
                for field, old_val in old.items():
                    if new.get(field) != old_val:
                        problems.append(f"[{cid}] {kind[:-1]} {eid} ({old.get('name')!r}): {field}: {old_val!r} -> {new.get(field)!r}")
    return problems


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("snapshot")
    sp.add_argument("--out", type=Path, required=True)
    sp.add_argument("--companies", help="через запятую; по умолчанию все доступные")
    sp.add_argument("--max-per-company", type=int, default=1000)
    cp = sub.add_parser("compare")
    cp.add_argument("baseline", type=Path)
    cp.add_argument("--companies")
    cp.add_argument("--md", type=Path)
    args = p.parse_args()

    companies = [int(x) for x in args.companies.split(",")] if getattr(args, "companies", None) else None
    if args.cmd == "snapshot":
        snap = take_snapshot(companies, args.max_per_company)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(snap, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"saved {args.out}")
        return 0

    before = json.loads(args.baseline.read_text(encoding="utf-8"))
    after = take_snapshot(companies or [int(c) for c in before["companies"]])
    problems = compare(before, after)
    total = sum(len(c["layouts"]) + len(c["widgets"]) for c in before["companies"].values())
    report = [f"# Сверка лейаутов/виджетов: {before['env']} (снимок {before['taken_at']})", f"Проверено сущностей: {total}"]
    report += [f"Расхождений: {len(problems)}", *[f"- {x}" for x in problems[:500]]]
    text = "\n".join(report)
    print(text)
    if args.md:
        args.md.write_text(text, encoding="utf-8")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
