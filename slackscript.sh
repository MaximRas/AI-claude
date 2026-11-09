#!/usr/bin/env bash
# Уведомление в Slack после прогона. Использование (after_script):
#   source ./slackscript.sh; sendNotification
# Нужен SLACK_WEBHOOK_URL (CI/CD variable, masked). Без него — тихо пропускаем.

sendNotification() {
  if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
    echo "SLACK_WEBHOOK_URL не задан — уведомление пропущено"
    return 0
  fi
  python ci/scripts/notify_slack.py \
    --junit "logs/report_${TEST_ENV:-alphatest1}.xml" \
    --title "API autotests [${TEST_ENV:-alphatest1}] ${TEST_MARK:-regression}" \
    || echo "WARN: не удалось отправить уведомление в Slack"
}
