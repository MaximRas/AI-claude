"""Сверка лейаутов/виджетов/шаринга с прод-снимком, сделанным ДО релиза (tools.layout_baseline).

Запуск после деплоя релиза:
    LAYOUT_BASELINE_FILE=reports/layout_baseline_staging.json pytest -m release_check
Без LAYOUT_BASELINE_FILE тест пропускается.
"""

import json
import os
from pathlib import Path

import allure
import pytest

from tools.layout_baseline import compare, take_snapshot

pytestmark = [pytest.mark.release_check]


@allure.feature("layout-manager")
@allure.story("release: данные до/после миграции")
def test_layouts_widgets_sharing_unchanged_after_release(settings):
    path = os.getenv("LAYOUT_BASELINE_FILE")
    if not path:
        pytest.skip("LAYOUT_BASELINE_FILE не задан: сначала `python -m tools.layout_baseline snapshot` до релиза")
    before = json.loads(Path(path).read_text(encoding="utf-8"))
    assert before["env"] == settings.env_name, f"снимок сделан на {before['env']}, а тесты идут на {settings.env_name}"
    after = take_snapshot([int(c) for c in before["companies"]])
    problems = compare(before, after)
    allure.attach("\n".join(problems) or "OK", name="расхождения", attachment_type=allure.attachment_type.TEXT)
    assert not problems, f"{len(problems)} расхождений после релиза:\n" + "\n".join(problems[:50])
