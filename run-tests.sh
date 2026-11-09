#!/usr/bin/env bash
# Запуск API-автотестов (локально и в GitLab CI).
#
# Переменные:
#   TEST_ENV        окружение из config/config.yaml                (по умолчанию alphatest1)
#   ALLOW_PRODUCTION=true — обязательно для prod-окружений (mymetapix, mydw)
#   TEST_MARK       pytest -m выражение: smoke | regression | "smoke and not destructive" | all
#   TEST_PATH       что запускать (по умолчанию tests)
#   PYTEST_WORKERS  параллельность xdist                            (по умолчанию 4; 0 — без xdist)
#   PYTEST_EXTRA    доп. аргументы pytest
#   ALLURE_TESTPLAN_PATH  testplan из Allure TestOps (перезапуск выбранных тестов)
#   ALLURE_ENDPOINT/ALLURE_TOKEN/ALLURE_PROJECT_ID — если заданы и есть allurectl, результаты
#                   стримятся в TestOps через `allurectl watch`.
set -uo pipefail

cd "$(dirname "$0")" || exit 1

TEST_ENV="${TEST_ENV:-alphatest1}"
TEST_MARK="${TEST_MARK:-}"
TEST_PATH="${TEST_PATH:-tests}"
PYTEST_WORKERS="${PYTEST_WORKERS:-4}"
ALLURE_RESULTS="${ALLURE_RESULTS:-allure-results}"
ALLURE_REPORT_DIR="${ALLURE_REPORT_DIR:-allure_report}"
export TEST_ENV ALLURE_RESULTS

# окружения — ключи верхнего уровня config/config.yaml
if ! grep -qE "^${TEST_ENV}:" config/config.yaml && [[ -z "${API_BASE_URL:-}" ]]; then
  echo "ERROR: неизвестный TEST_ENV='${TEST_ENV}'. Доступны: $(python -c 'from config.settings import config_environments as c; print(" ".join(c()))')" >&2
  exit 2
fi

mkdir -p logs "${ALLURE_RESULTS}"

# --- выбор тестов ---
# "regression" = всё, кроме самотестов фреймворка; "all" — то же, явно
case "${TEST_MARK}" in
  "" | all | regression) MARK_EXPR="not selftest" ;;
  *) MARK_EXPR="(${TEST_MARK}) and not selftest" ;;
esac

# --- testplan из Allure TestOps (запуск выбранных тестов из UI TestOps) ---
if [[ -n "${ALLURE_TESTPLAN_PATH:-}" ]]; then
  if [[ -n "${ALLURE_JOB_RUN_ID:-}" ]] && command -v allurectl >/dev/null 2>&1; then
    allurectl job-run plan --output-file "${ALLURE_TESTPLAN_PATH}" || echo "WARN: testplan не получен"
  fi
  if [[ -s "${ALLURE_TESTPLAN_PATH}" ]]; then
    echo "Allure testplan: ${ALLURE_TESTPLAN_PATH}"
    export ALLURE_TESTPLAN_PATH            # allure-pytest сам отфильтрует тесты
  else
    unset ALLURE_TESTPLAN_PATH
  fi
fi

PYTEST_ARGS=(
  "${TEST_PATH}"
  -m "${MARK_EXPR}"
  --alluredir="${ALLURE_RESULTS}"
  --junitxml="logs/report_${TEST_ENV}.xml"
  -o log_cli=false
  --log-file="logs/pytest_${TEST_ENV}.log"
  --log-file-level=DEBUG
  -p no:cacheprovider
)
if [[ "${PYTEST_WORKERS}" != "0" ]]; then
  PYTEST_ARGS+=(-n "${PYTEST_WORKERS}")
fi
if [[ -n "${PYTEST_EXTRA:-}" ]]; then
  # shellcheck disable=SC2206 # намеренное разбиение на аргументы
  PYTEST_ARGS+=(${PYTEST_EXTRA})
fi

echo "TEST_ENV=${TEST_ENV}  TEST_MARK=${TEST_MARK:-<all>}  -m '${MARK_EXPR}'  workers=${PYTEST_WORKERS}"

if command -v allurectl >/dev/null 2>&1 && [[ -n "${ALLURE_ENDPOINT:-}" && -n "${ALLURE_TOKEN:-}" ]]; then
  allurectl watch --results "${ALLURE_RESULTS}" -- python -m pytest "${PYTEST_ARGS[@]}"
  rc=$?
else
  python -m pytest "${PYTEST_ARGS[@]}"
  rc=$?
fi

# Сырые allure-results в артефакт (отчёт строится в TestOps / `allure serve`)
rm -rf "${ALLURE_REPORT_DIR}" && cp -r "${ALLURE_RESULTS}" "${ALLURE_REPORT_DIR}"

# pytest: 5 = не собрано ни одного теста (например, пустой testplan) — не считаем падением
if [[ ${rc} -eq 5 ]]; then
  echo "WARN: не выбрано ни одного теста"
  rc=0
fi
exit ${rc}
