"""Сводка прогона в Slack (incoming webhook) на requests.

    python ci/scripts/notify_slack.py --junit logs/report_alphatest1.xml --title "API autotests"
    python ci/scripts/notify_slack.py --text "Агент открыл MR ..."      # произвольное сообщение

Переменные: SLACK_WEBHOOK_URL; из GitLab CI берутся CI_JOB_URL, CI_PIPELINE_URL, CI_JOB_STATUS,
CI_COMMIT_REF_NAME, GITLAB_USER_NAME; ссылка на запуск TestOps — ALLURE_ENDPOINT + ALLURE_LAUNCH_ID (если есть).
"""

from __future__ import annotations

import argparse
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import requests


def junit_summary(path: Path) -> dict[str, int] | None:
    if not path.exists():
        return None
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    total = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    for s in suites:
        for key in total:
            total[key] += int(s.get(key, 0) or 0)
    total["passed"] = total["tests"] - total["failures"] - total["errors"] - total["skipped"]
    return total


def build_message(title: str, summary: dict[str, int] | None) -> dict:
    env = os.environ
    status = env.get("CI_JOB_STATUS", "")
    failed = bool(summary and (summary["failures"] or summary["errors"])) or status == "failed"
    icon = ":red_circle:" if failed else (":large_green_circle:" if summary else ":white_circle:")
    lines = [f"{icon} *{title}*"]
    if summary:
        lines.append(
            f"passed: *{summary['passed']}*  failed: *{summary['failures']}*  errors: *{summary['errors']}*"
            f"  skipped: {summary['skipped']}  total: {summary['tests']}"
        )
    else:
        lines.append("_junit-отчёт не найден — тесты не запускались или упали до старта_")
    links = []
    if env.get("CI_JOB_URL"):
        links.append(f"<{env['CI_JOB_URL']}|job>")
    if env.get("CI_PIPELINE_URL"):
        links.append(f"<{env['CI_PIPELINE_URL']}|pipeline>")
    if env.get("ALLURE_ENDPOINT") and env.get("ALLURE_LAUNCH_ID"):
        links.append(f"<{env['ALLURE_ENDPOINT'].rstrip('/')}/launch/{env['ALLURE_LAUNCH_ID']}|Allure TestOps>")
    meta = " · ".join(x for x in [env.get("CI_COMMIT_REF_NAME"), env.get("CI_PIPELINE_SOURCE"), env.get("GITLAB_USER_NAME")] if x)
    lines.append(" | ".join(links) + (f"   _{meta}_" if meta else ""))
    return {"text": "\n".join(lines)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--junit", type=Path)
    p.add_argument("--title", default="API autotests")
    p.add_argument("--text", help="отправить произвольный текст вместо сводки")
    args = p.parse_args()

    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        print("SLACK_WEBHOOK_URL не задан")
        return 0
    payload = {"text": args.text} if args.text else build_message(args.title, junit_summary(args.junit) if args.junit else None)
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    print("slack: sent")
    return 0


if __name__ == "__main__":
    sys.exit(main())
