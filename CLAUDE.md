# metapix-api-tests — инструкции для Claude Code

Black-box API-автотесты микросервисов metapix (auth-manager, object-manager [+ device-manager,
watchlist-manager, chartilla], layout-manager) на **requests + pytest + pydantic v2**, с контрактной
проверкой ответов по OpenAPI (`specs/*.json`).

## Структура
- `config/settings.py` — все настройки: ENV > `.env` > `config/config.yaml` (окружения, формат как у фронта, без секретов) > дефолты.
- `framework/` — ядро: `http_client.py` (ApiClient/ApiResponse на requests), `routing.py` (путь спеки → URL gateway),
  `openapi.py` (валидация ответа по спеке), `auth.py` (логин/кэш токена), `markers.py` (`@endpoint`), `cleanup.py`, `data.py`.
- `services/<svc>/client.py|models.py` — клиенты и модели доменов. Пути — ровно как в спеке.
- `tests/<domain>/` — тесты; `tests/fixtures/` — клиенты и фабрики (с автоочисткой).
- `tools/` — `fetch_specs`, `spec_diff`, `coverage`, `mr_impact`, `dump_openapi`.
- `.claude/` — skill `api-autotest-writer`, субагенты `api-impact-analyzer`, `api-test-writer`, команды `/mr-tests`, `/cover-endpoint`.

## Главные правила
1. Каждый тест помечен `@endpoint(service, METHOD, path_из_спеки)`.
2. На каждый успешный ответ — `.assert_contract()`.
3. Сущности создаются фабриками с `cleanup`; имена — `unique_name()` (префикс `autotest_`).
4. Никаких секретов/id/URL стенда в коде. `.env` не читать и не коммитить.
5. Опасные эндпоинты — `tools/coverage_ignore.yaml`; неудаляемые сущности — маркер `destructive`.
6. Перед завершением: `ruff check . && ruff format --check . && pytest -m selftest -q && pytest --collect-only -q`.

Подробности написания тестов — `.claude/skills/api-autotest-writer/SKILL.md`.

## Gateway
`/public/<rest>` → `/<service>/<rest>`; `/<prefix>/public/<rest>` → `/<prefix>/<rest>`; `/private/*` (кроме health) снаружи
недоступны — такие тесты автоматически skip при `API_ROUTING=gateway`. Ошибки: `{code, status:"error", message, error_code?, fields?}`.
Без токена gateway отвечает `403 INVALID_ACCESS_TOKEN_ERROR`. Заголовок токена — `access-token`.
После логина токен не привязан к компании (всё → `403 COMPANY_NOT_SELECTED_ERROR`); `framework/auth.py` сам вызывает
`PATCH /context/active-company` с `TEST_COMPANY_ID` (контекст per-token). Тестовая компания: 10055 «Maxim Rasulzoda».
422: `fields[].field_name` = имя поля тела или "path"/"query", точное поле — в `fields[].full_path` (`query.timestamp_start`).

## Тестовый пользователь
Везде используется `TEST_USER_LOGIN`/`TEST_USER_PASSWORD` из `.env` (локально) или CI-переменных. Не вписывай креды в код.
