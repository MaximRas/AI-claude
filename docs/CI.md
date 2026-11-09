# GitLab CI: API-автотесты + Claude-агент

CI построен по образцу фронтовых автотестов: образ в GitLab Registry, раннер `special::qa`,
Allure TestOps через `allurectl`, запуск `./run-tests.sh`, уведомление `slackscript.sh`.
Дополнительно — стадия `agent` с Claude Code.

## Пайплайн

| Стадия | Джоба | Когда | Что делает |
|---|---|---|---|
| build | **Build Image** | изменения `Dockerfile`/`requirements.txt`/`.gitlab-ci.yml`, MR в master, master, `release_x.y.zz` | 2 образа: `runtime` (`$IMAGE_FULL_REF`) и `agent` (`$IMAGE_AGENT_REF`), проверка `allurectl auth login` и `claude --version` |
| lint | **Lint**, **Selftest** | MR, master | ruff, `bash -n`, самотесты фреймворка, сбор тестов, отчёт покрытия |
| test | **Run tests** | schedule, запуск из TestOps, trigger из сервиса (smoke после деплоя), MR `autotests/*` от агента, вручную | `allurectl job-run start` → `./run-tests.sh` → Slack |
| agent | **Claude: MR impact** | trigger из MR сервиса (`AGENT_TASK=mr-impact`) | разбор diff → комментарий в MR сервиса → MR с тестами в этот репо |
| agent | **Claude: cover uncovered** | Run pipeline с `AGENT_TASK=cover`, `SERVICE_NAME=…` | тесты на непокрытые эндпоинты → MR |
| agent | **Claude: specs sync** | расписание с `AGENT_TASK=specs-sync` | `fetch_specs` → при изменениях обновить тесты → MR |

Пайплайн с `AGENT_TASK` запускает только агент (Run tests и Build пропускаются).

## CI/CD Variables (Settings → CI/CD → Variables)

### Обязательные

| Переменная | Пример | Masked | Protected | Назначение |
|---|---|---|---|---|
| `TEST_USER_LOGIN` | `mrasulzoda@metapix.ai` | – | – | тестовый пользователь |
| `TEST_USER_PASSWORD` | `••••` | да* | да | пароль тестового пользователя |
| `ALLURE_ENDPOINT` | `https://<testops>` | – | – | Allure TestOps (как во фронте) |
| `ALLURE_TOKEN` | `••••` | да | – | токен TestOps |
| `ALLURE_PROJECT_ID` | `42` | – | – | **отдельный** проект TestOps для API (или тот же, с тегом `api`) |
| `SLACK_WEBHOOK_URL` | `https://hooks.slack.com/…` | да | – | уведомления (`slackscript.sh`) |

\* GitLab маскирует только значения из ≥8 символов без части спецсимволов; если пароль не маскируется
(`!` в `String!2`), сделайте переменную **Protected** и ограничьте доступ к репо, либо смените пароль на маскируемый.

### Для агента

| Переменная | Masked | Назначение |
|---|---|---|
| `ANTHROPIC_API_KEY` | да | ключ Claude API (Console → API keys). Альтернативы ниже |
| `GITLAB_API_TOKEN` | да | Project/Group Access Token бота: scope `api`, `write_repository`; роль Developer в этом репо и Reporter+ в репо сервисов (клон + комментарии в MR) |
| `CLAUDE_MODEL` | – | (опц.) модель: алиас `sonnet` / `opus` или полный ID; по умолчанию — модель CLI |
| `CLAUDE_MAX_TURNS` | – | (опц.) лимит шагов агента, по умолчанию 80 |
| `AGENT_WRITE_TESTS` | – | (опц.) `false` — только план проверки и комментарий, без MR с тестами |

Альтернативы `ANTHROPIC_API_KEY` для корпоративного контура:
- **AWS Bedrock:** `CLAUDE_CODE_USE_BEDROCK=1`, `AWS_REGION`, `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (или роль раннера).
- **Google Vertex AI:** `CLAUDE_CODE_USE_VERTEX=1`, `CLOUD_ML_REGION`, `ANTHROPIC_VERTEX_PROJECT_ID`, `GOOGLE_APPLICATION_CREDENTIALS`.
- **Подписка Claude (Team/Enterprise):** `CLAUDE_CODE_OAUTH_TOKEN` (получить: `claude setup-token`).
- Корпоративный прокси: `HTTPS_PROXY`, `NODE_EXTRA_CA_CERTS=/path/ca.pem`.

### Необязательные (переопределяют профиль стенда)

`TEST_ENV` (alphatest1), `TEST_MARK` (smoke), `TEST_COMPANY_ID`, `API_BASE_URL`, `PYTEST_WORKERS` (4),
`ALLOW_DESTRUCTIVE` (false), `SECOND_USER_LOGIN`/`SECOND_USER_PASSWORD`, `STRICT_CONTRACT`.

### Окружения — `config/config.yaml`

Формат тот же, что у `config.yaml` фронтовых автотестов (якоря `&dev_env` / `<<: *dev_env` работают),
но **без секретов** — файл коммитится, а selftest `test_no_secrets_in_config_yaml` падает, если секрет туда попадёт.
Для API-тестов в секцию окружения добавлен блок `api_tests` (`company_id`, `routing`, `production`).

| TEST_ENV | API | Компания для тестов | Prod |
|---|---|---|---|
| alphatest1, dev-dw, dev-metapix | api.alphatest1.dev.metapixai.com | 10055 | – |
| staging, staging-metapix | api.staging.metapix.ai | задать `TEST_COMPANY_ID` | – |
| mymetapix | api.my.metapix.ai | задать `TEST_COMPANY_ID` | да |
| mydw | api.mydw.metapix.ai | задать `TEST_COMPANY_ID` | да |

Prod-окружения запускаются только с `ALLOW_PRODUCTION=true` (иначе pytest завершится с ошибкой ещё до сбора тестов).

### Секреты окружений (CI/CD variables, masked)

| Переменная | Откуда в старом config.yaml | Нужна для |
|---|---|---|
| `GITLAB_API_TOKEN` | `gitlab.private_token` | агент (клон сервисов, MR, комментарии) |
| `TEST_USER_PASSWORD` | `_default_pwd` | логин тестового пользователя |
| `COGNITO__ACCESS_KEY`, `COGNITO__SECRET_KEY` | `<env>.cognito.access_key/secret_key` | сценарии с Cognito (подтверждение/создание пользователей) |
| `MAILINATOR_TOKEN` | `mailinator.token` | сценарии с письмами (forgot-password, register) |
| `DWNX__PASSWORD` | `DWNX.password` | SSO NX/DW |

Ключи Cognito, креды и компании различаются у dev / staging / prod — заводите их как **environment-scoped variables**
(Settings → CI/CD → Variables → *Environment scope*: `alphatest1`, `dev-*`, `staging*`, `mymetapix`, `mydw`; для общих — `*`).
Джобы `Run tests` и `Claude: *` объявляют `environment: name: $TEST_ENV, action: access` — GitLab подставит переменные
нужного окружения, деплоев при этом не создаётся. Для prod-окружений включите Protected environments.

## Сеть раннера `special::qa`

Раннер должен иметь доступ к: стенду (`api.alphatest1.dev.metapixai.com`), GitLab, Registry, Allure TestOps,
Slack, а для агента — `api.anthropic.com` (или Bedrock/Vertex), `registry.npmjs.org` и `deb.nodesource.com`
(только при сборке образа), `github.com` (скачивание allurectl при сборке).

## Расписания (CI/CD → Schedules)

| Название | Ветка | Переменные | Cron |
|---|---|---|---|
| API smoke | master | `TEST_ENV=alphatest1`, `TEST_MARK=smoke` | `0 */3 * * 1-5` |
| API regression nightly | master | `TEST_ENV=alphatest1`, `TEST_MARK=regression` | `0 2 * * *` |
| API specs sync (agent) | master | `AGENT_TASK=specs-sync`, `TEST_ENV=alphatest1` | `30 6 * * 1-5` |

## Allure TestOps

- `before_script`: `allurectl job-run start` (как во фронте), launch с тегами `api,<TEST_MARK>`.
- `run-tests.sh`: при запуске из TestOps (`ALLURE_JOB_RUN_ID`) берёт testplan (`allurectl job-run plan`
  → `$ALLURE_TESTPLAN_PATH`), allure-pytest запускает только выбранные тесты; результаты стримятся через `allurectl watch`.
- В TestOps настройте Job для этого проекта GitLab (как для фронта), пользователь интеграции — `allure-testops-integration`
  или `gitlab+pat-allure-testops` (уже в rules). Параметры джобы TestOps → `TEST_ENV`, `TEST_MARK`.

## Подключение сервисов

В `.gitlab-ci.yml` каждого сервиса:

```yaml
include:
  - project: "metapix-cloud/qa/metapix-api-tests"   # путь к этому репо
    ref: master
    file: "/ci/service-mr.gitlab-ci.yml"

variables:
  API_TESTS_SERVICE: "object-manager"               # auth-manager | layout-manager | ...
  API_TESTS_DEPLOY_BRANCH: "dev"
```

Что появится в сервисе:
- `api-tests:mr-agent` (stage `test`, на каждый не-draft MR, не блокирует) — trigger в этот репо с `AGENT_TASK=mr-impact`.
  Через ~3–5 мин в MR сервиса появится (обновляемый) комментарий: затронутые эндпоинты, риск, breaking changes,
  какие тесты гонять, что проверить вручную + ссылка на MR с новыми тестами.
- `api-tests:smoke` (stage `deploy`, ветка `dev`) — smoke API после деплоя, статус виден в пайплайне сервиса.

Секреты Claude/GitLab хранятся **только** в репозитории автотестов — в сервисы ничего добавлять не нужно.

## Локальная отладка

```bash
cp .env.example .env                 # креды
./run-tests.sh                       # TEST_MARK=smoke ./run-tests.sh
# агент без пушей и комментариев:
AGENT_TASK=mr-impact AGENT_DRY_RUN=true SERVICE_REPO_DIR=../object-manager \
  SERVICE_PROJECT_PATH=metapix-cloud/backend/object-manager SERVICE_MR_IID=1 \
  SERVICE_SOURCE_SHA=HEAD SERVICE_TARGET_BRANCH=dev ./run-agent.sh
# образ:
docker build --target agent -t api-tests-agent . && docker run --rm --env-file .env api-tests-agent
```

## Стоимость агента

E2E на тестовом MR (3 изменения → 9 тестов): ~3–4 мин, ~$0.5 на MR (Opus-класс). Для экономии:
`CLAUDE_MODEL=sonnet`, `AGENT_WRITE_TESTS=false` на MR (только анализ), агент не запускается на draft-MR.
