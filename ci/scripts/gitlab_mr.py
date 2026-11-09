"""Мини-клиент GitLab API на requests: комментарий в MR сервиса и MR с тестами в репо автотестов.

    python ci/scripts/gitlab_mr.py note --project $CI_PROJECT_ID --mr $CI_MERGE_REQUEST_IID --file reports/mr_comment.md
    python ci/scripts/gitlab_mr.py open-mr --project $API_TESTS_PROJECT_ID --source autotests/x --target main \
        --title "..." --description-file reports/agent_report.md

Переменные: GITLAB_API_TOKEN (scope api), CI_API_V4_URL (есть в GitLab CI).
Комментарий с маркером <!-- api-impact --> обновляется, а не дублируется при каждом пуше в MR.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import quote

import requests

MARKER = "<!-- api-impact -->"


def _session() -> tuple[requests.Session, str]:
    token = os.environ.get("GITLAB_API_TOKEN")
    if not token:
        sys.exit("GITLAB_API_TOKEN не задан")
    s = requests.Session()
    s.headers["PRIVATE-TOKEN"] = token
    api = os.environ.get("CI_API_V4_URL")
    if not api:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from config.settings import get_settings

        api = get_settings().gitlab_host.rstrip("/") + "/api/v4"
    return s, api.rstrip("/")


def _pid(project: str) -> str:
    return project if project.isdigit() else quote(project, safe="")


def upsert_note(project: str, mr: str, body: str) -> None:
    s, api = _session()
    url = f"{api}/projects/{_pid(project)}/merge_requests/{mr}/notes"
    body = f"{MARKER}\n{body}"
    notes = s.get(url, params={"per_page": 100, "sort": "desc"}, timeout=30)
    notes.raise_for_status()
    existing = next((n for n in notes.json() if MARKER in (n.get("body") or "")), None)
    if existing:
        s.put(f"{url}/{existing['id']}", json={"body": body}, timeout=30).raise_for_status()
        print(f"note {existing['id']} updated")
    else:
        resp = s.post(url, json={"body": body}, timeout=30)
        resp.raise_for_status()
        print(f"note {resp.json()['id']} created")


def open_mr(project: str, source: str, target: str, title: str, description: str) -> str:
    s, api = _session()
    base = f"{api}/projects/{_pid(project)}/merge_requests"
    existing = s.get(base, params={"source_branch": source, "state": "opened"}, timeout=30)
    existing.raise_for_status()
    if existing.json():
        mr = existing.json()[0]
        s.put(f"{base}/{mr['iid']}", json={"description": description}, timeout=30).raise_for_status()
        return mr["web_url"]
    resp = s.post(
        base,
        json={"source_branch": source, "target_branch": target, "title": title, "description": description, "remove_source_branch": True},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["web_url"]


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("note")
    n.add_argument("--project", required=True)
    n.add_argument("--mr", required=True)
    n.add_argument("--file", type=Path, required=True)
    n.add_argument("--append", default="", help="доп. текст в конец (например ссылка на MR с тестами)")
    o = sub.add_parser("open-mr")
    o.add_argument("--project", required=True)
    o.add_argument("--source", required=True)
    o.add_argument("--target", default="main")
    o.add_argument("--title", required=True)
    o.add_argument("--description-file", type=Path)
    args = p.parse_args()

    if args.cmd == "note":
        text = args.file.read_text(encoding="utf-8") if args.file.exists() else "_агент не сформировал отчёт, см. артефакты job_"
        upsert_note(args.project, args.mr, text + ("\n\n" + args.append if args.append else ""))
    else:
        desc = args.description_file.read_text(encoding="utf-8") if args.description_file and args.description_file.exists() else ""
        print(open_mr(args.project, args.source, args.target, args.title, desc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
