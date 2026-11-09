"""Скачать актуальные OpenAPI-спеки со стенда в specs/.

    python -m tools.fetch_specs                       # стенд из API_BASE_URL
    python -m tools.fetch_specs --base-url https://api.alphatest1.dev.metapixai.com
    python -m tools.fetch_specs --check               # только показать diff, не сохранять (exit 1 при изменениях)

Файлы сохраняются отформатированными (indent=2, sort_keys) — так git diff спек читаемый.
Примечание: /chartilla/openapi.json на стенде отдаёт ту же спеку, что object-manager
(chartilla — роутер внутри object-manager), поэтому отдельно не хранится.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import get_settings  # noqa: E402
from tools.spec_diff import diff_specs, render_markdown  # noqa: E402

SPEC_URLS = {
    "object-manager": "/object-manager/openapi.json",
    "auth-manager": "/auth-manager/openapi.json",
    "layout-manager": "/layout-manager/openapi.json",
}


def dump(spec: dict) -> str:
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=settings.api_base_url)
    parser.add_argument("--out", type=Path, default=settings.specs_dir)
    parser.add_argument("--service", choices=sorted(SPEC_URLS), action="append", help="только указанные сервисы")
    parser.add_argument("--check", action="store_true", help="не сохранять, только сообщить об изменениях")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    changed = False
    for service in args.service or SPEC_URLS:
        url = args.base_url.rstrip("/") + SPEC_URLS[service]
        resp = requests.get(url, timeout=60, verify=settings.verify_ssl)
        resp.raise_for_status()
        new_spec = resp.json()
        target = args.out / f"{service}.json"
        old_spec = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {"paths": {}, "components": {}}
        report = diff_specs(old_spec, new_spec)
        if report["has_changes"]:
            changed = True
            print(f"## {service}: есть изменения\n{render_markdown(report)}")
        else:
            print(f"## {service}: без изменений")
        if not args.check:
            target.write_text(dump(new_spec), encoding="utf-8")
            print(f"   сохранено: {target.relative_to(ROOT) if target.is_relative_to(ROOT) else target}")
    return 1 if (args.check and changed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
