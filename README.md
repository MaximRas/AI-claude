# metapix-api-tests

Фреймворк и автотесты API для микросервисов metapix + AI-агент (Claude Code), который по diff MR
определяет, что проверять, и пишет тесты на новые/изменённые эндпоинты.

**Стек:** Python 3.10+, requests, pytest (+xdist), pydantic v2, jsonschema (контракт по OpenAPI), Allure.

## Быстрый старт

```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                              # TEST_USER_LOGIN / TEST_USER_PASSWORD / TEST_COMPANY_ID
python -m tools.fetch_specs                       # скачать спеки со стенда в specs/ (нужен доступ к стенду/VPN)
pytest -m selftest                                # самопроверка фреймворка (без стенда)
pytest -m smoke                                   # smoke против стенда
pytest -n 4                                       # весь регресс параллельно
pytest --alluredir=allure-results && allure serve allure-results
```

Без кредов запускаются только анонимные проверки (health, version, 401/403, валидация логина) —
остальные помечаются skip с причиной. Тесты `destructive` (камеры, servers/sites — без DELETE)
включаются `ALLOW_DESTRUCTIVE=true`; тесты шаринга — при наличии `SECOND_USER_*`.

## Структура

```
config/config.yaml            окружения (alphatest1, dev-dw, staging, mymetapix, ...) — без секретов
config/settings.py            настройки: ENV > .env > config.yaml
framework/
  http_client.py              ApiClient (requests.Session, ретраи, логирование, curl в Allure) + ApiResponse (fluent-ассерты)
  routing.py                  путь из спеки -> URL (gateway | direct)
  openapi.py                  контрактная валидация ответа по specs/<service>.json
  auth.py                     логин в auth-manager, кэш токенов
  markers.py                  @endpoint(service, method, path) — связь теста со спекой
  cleanup.py, data.py         teardown-реестр, генераторы данных
services/
  auth_manager/               AuthManagerClient + модели
  object_manager/             ObjectManager / DeviceManager / WatchlistManager / Chartilla клиенты (+ private)
  layout_manager/             LayoutManagerClient + модели
tests/
  fixtures/                   клиенты (*_api, anon_*), фабрики сущностей с автоудалением
  auth_manager/ object_manager/ device_manager/ watchlist_manager/ chartilla/ layout_manager/
  framework_selftest/         тесты самого фреймворка и инструментов (на моках)
tools/
  fetch_specs.py              скачать спеки + показать diff
  spec_diff.py                семантический diff двух версий спеки
  coverage.py                 покрытие эндпоинтов тестами (+ coverage_ignore.yaml)
  mr_impact.py                анализ diff MR сервиса -> затронутые эндпоинты/тесты
  dump_openapi.py             openapi.json из кода FastAPI (для CI MR)
.claude/                      skill, субагенты и команды для Claude Code
ci/service-mr.gitlab-ci.yml   job для репозиториев сервисов (агент на MR)
```

## Как выглядит тест

```python
@endpoint("object-manager", "PATCH", "/watchlist-manager/public/v1/watchlists/{watchlist_id}")
def test_rename(self, watchlists_api, watchlist_factory, me):
    wl = watchlist_factory()  # создаст и удалит после теста
    new_name = unique_name("watchlist_renamed")
    body = (
        watchlists_api.patch_watchlist(wl["id"], new_name)
        .assert_status(200)
        .assert_contract()  # ответ соответствует спеке
        .json()
    )
    assert body["name"] == new_name
```

Пути пишутся как в спеке; на стенде запрос уйдёт через gateway (`/watchlist-manager/v1/watchlists/1`).
Для локального сервиса: `API_ROUTING=direct OBJECT_MANAGER_URL=http://localhost:8000`.

## Покрытие

```bash
python -m tools.coverage                         # все сервисы
python -m tools.coverage --service layout-manager --uncovered
```

## Агент для MR

### Локально (Claude Code)
```bash
cd metapix-api-tests
claude
> /mr-tests ../object-manager origin/dev          # анализ + тесты
> /mr-tests ../object-manager origin/dev --no-write   # только план проверки
> /cover-endpoint layout-manager --uncovered      # дописать тесты на непокрытое
```
Конвейер: `tools.mr_impact` (детерминированно: AST роутеров, pydantic-схемы → эндпоинты через `$ref`
в спеке, call-graph изменённых функций, существующие тесты) → субагент **api-impact-analyzer**
(читает diff, уточняет, пишет `reports/test_plan.json`) → субагент **api-test-writer** (пишет тесты по
skill `api-autotest-writer`, прогоняет lint/selftest/collect) → `reports/mr_comment.md`.

Только детерминированная часть, без LLM:
```bash
python -m tools.mr_impact --repo ../object-manager --base origin/dev --md reports/impact.md
```

### В GitLab CI
Полная настройка — **[docs/CI.md](docs/CI.md)**: стадии, CI/CD variables, расписания, Allure TestOps, подключение сервисов.
Кратко: `.gitlab-ci.yml` повторяет схему фронтовых автотестов (образ в Registry, `special::qa`, `allurectl`,
`./run-tests.sh`, `slackscript.sh`) и добавляет стадию `agent` (`./run-agent.sh`: `mr-impact` | `cover` | `specs-sync`).
Сервисы подключают `ci/service-mr.gitlab-ci.yml` — trigger-джобы без секретов.

## Обновление спек
```bash
python -m tools.fetch_specs --check    # что изменилось на стенде (exit 1 при изменениях)
python -m tools.fetch_specs            # сохранить
git diff specs/
```
Расписание `specs-drift` в CI сигнализирует о расхождении спек стенда и репозитория.
