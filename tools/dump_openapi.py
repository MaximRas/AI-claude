"""Сгенерировать openapi.json из кода FastAPI-сервиса (без запуска сервера).

Запускается в окружении СЕРВИСА (где установлены его зависимости), например в CI MR:
    python dump_openapi.py object_manager.main:app /tmp/openapi.json

Импорт приложения может требовать переменных окружения сервиса (DATABASE_URL и т.п.) —
подставьте фиктивные значения. Если импорт не удался, mr_impact работает и без новой спеки
(по AST и старой спеке), просто с меньшей точностью.
"""

from __future__ import annotations

import importlib
import json
import sys


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 2
    target, out = sys.argv[1], sys.argv[2]
    module_name, _, attr = target.partition(":")
    app = getattr(importlib.import_module(module_name), attr or "app")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(app.openapi(), fh, indent=2, sort_keys=True, ensure_ascii=False)
    print(f"saved {out}: {len(app.openapi().get('paths', {}))} paths")
    return 0


if __name__ == "__main__":
    sys.exit(main())
