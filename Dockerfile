# Образ для API-автотестов metapix.
#   runtime — python + зависимости + allurectl (джоба "Run tests")
#   agent   — runtime + Node.js + Claude Code CLI (джобы "Claude: ...")
#
#   docker build --target runtime -t <registry>/metapix-api-tests:<ref> .
#   docker build --target agent   -t <registry>/metapix-api-tests/agent:<ref> .

ARG PYTHON_VERSION=3.12

FROM python:${PYTHON_VERSION}-slim AS runtime

ARG ALLURECTL_URL=https://github.com/allure-framework/allurectl/releases/latest/download/allurectl_linux_amd64

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ALLURE_RESULTS=allure-results

# procps — для `pkill allurectl` в after_script; git — для агента и spec_diff --git-ref
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl git procps \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL -o /usr/local/bin/allurectl "${ALLURECTL_URL}" \
    && chmod +x /usr/local/bin/allurectl \
    && allurectl --version

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# Код копируется для автономного `docker run`; в GitLab CI джоба работает в checkout репозитория.
COPY . .
RUN chmod +x run-tests.sh run-agent.sh

CMD ["./run-tests.sh"]


FROM runtime AS agent

ARG NODE_MAJOR=20
ARG CLAUDE_CODE_VERSION=latest

RUN curl -fsSL "https://deb.nodesource.com/setup_${NODE_MAJOR}.x" | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
    && npm cache clean --force \
    && claude --version

# В CI автообновление и телеметрия CLI не нужны
ENV DISABLE_AUTOUPDATER=1 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

CMD ["./run-agent.sh"]
