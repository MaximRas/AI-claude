<!-- Пример: результат /mr-tests на синтетическом MR в object-manager (новый GET /watchlists/{id}, поле description в WatchlistModifySchema, правка modify_watchlist). Агент нашёл, что get_watchlist не существует. -->

## API-анализ MR (object-manager) — риск: **high**

**Что меняет MR**
- Новый `GET /watchlist-manager/public/v1/watchlists/{watchlist_id}`. Тестов не было.
  - Обработчик вызывает `watchlist_queries.get_watchlist`, а такой функции в `db/queries/watchlist.py` нет — вероятно, 500 (AttributeError) на любой запрос.
  - `NoEntryFoundException` не ловится (в отличие от PATCH/DELETE): для несуществующего id вместо 404 возможен 500.
- `PATCH .../watchlists/{watchlist_id}`: в `WatchlistModifySchema` добавлено опциональное `description`, но `modify_watchlist` его не сохраняет, поля нет ни в модели `Watchlist`, ни в миграциях. Значение принимается и молча теряется.

**Breaking changes**
- Явных нет: новый эндпоинт и необязательное поле. `name` в PATCH остаётся обязательным.

**Существующие тесты для запуска**
```
pytest "tests/watchlist_manager/test_watchlists.py::TestWatchlists::test_rename" "tests/watchlist_manager/test_watchlists.py::TestWatchlists::test_rename_not_found" "tests/watchlist_manager/test_watchlists.py::TestWatchlists::test_rename_to_existing_name"
```
Новые тесты: `pytest tests/watchlist_manager/test_watchlists.py -m generated`

**Добавлено / изменено**
- `TestGetWatchlist` (успех, 404, 404 после удаления, 422 на нечисловой id, авторизация).
- 4 теста PATCH с `description` (с именем, сохранение, без `name` → 422, `null`).
- `WatchlistManagerClient.get_watchlist`, `patch_watchlist(**fields)`, доп. поля модели `Watchlist`.
- В спеке нового GET нет: хелпер `assert_watchlist_contract` проверяет по спеке, если эндпоинт в ней есть, иначе по pydantic-модели.
- Против стенда тесты не запускались (нет кредов/сети). Selftest: 32 passed; collect: 279 тестов.
  `ruff format --check` падает на 8 файлах, которых MR-тесты не меняли.

**Проверить вручную**
- Где реализована `get_watchlist`; ожидаем, что GET-тесты упадут с 500, пока это не исправлено.
- Нужно ли хранить `description` (если нет — удалить или инвертировать `test_description_is_persisted`).
- Изоляцию по `company_id` для нового GET (нужен пользователь из другой компании).
- Обновить `specs/*.json` (`python -m tools.fetch_specs`).
