"""Самотесты загрузки окружений из config/config.yaml."""

import os
import subprocess
import sys

import pytest

from config.settings import ROOT_DIR, config_environments

pytestmark = pytest.mark.selftest

PROBE = (
    "from config.settings import get_settings as g; s=g(); "
    "print(s.env_name, s.api_base_url, s.web_url, s.theme, s.test_company_id, s.production, s.request_timeout, "
    "s.cognito.region_name, s.service_provider.company_name_cpo, bool(s.cognito.secret_key))"
)


def settings_for(**env) -> list[str]:
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("TEST_", "API_", "COGNITO", "REQUEST_TIMEOUT"))}
    out = subprocess.run([sys.executable, "-c", PROBE], env={**clean, **env}, cwd=ROOT_DIR, capture_output=True, text=True, check=True)
    return out.stdout.split()


def test_environments_list():
    assert set(config_environments()) == {"alphatest1", "dev-dw", "dev-metapix", "mymetapix", "mydw", "staging", "staging-metapix", "object-ng"}


def test_no_secrets_in_config_yaml():
    """config.yaml коммитится: секреты допустимы только в комментариях-подсказках (`# env: ...`)."""
    forbidden = ("glpat-", "AKIA", "secret_key", "access_key", "private_token", "password", "token")
    for n, line in enumerate((ROOT_DIR / "config" / "config.yaml").read_text(encoding="utf-8").splitlines(), 1):
        code = line.split("#", 1)[0]
        assert not any(f in code for f in forbidden), f"config.yaml:{n}: похоже на секрет: {line.strip()}"


def test_alphatest1_defaults():
    name, url, web, theme, company, prod, *_ = settings_for(TEST_ENV="alphatest1")
    assert (name, url, web, company, prod) == (
        "alphatest1",
        "https://api.alphatest1.dev.metapixai.com",
        "https://app.alphatest1.dev.metapixai.com",
        "10055",
        "False",
    )


def test_yaml_anchor_inheritance():
    name, url, web, theme, company, *_ = settings_for(TEST_ENV="dev-dw")
    assert url == "https://api.alphatest1.dev.metapixai.com", "url унаследован от alphatest1 через <<: *dev_env"
    assert (web, theme, company) == ("https://dev.dw.front.fbt.dev.metapixai.com", "dw", "10055")


def test_env_overrides_yaml_and_nested_secret():
    vals = settings_for(TEST_ENV="staging-metapix", TEST_COMPANY_ID="777", COGNITO__SECRET_KEY="x", REQUEST_TIMEOUT="5,7")
    assert vals[1] == "https://api.staging.metapix.ai"
    assert vals[4] == "777"
    assert " ".join(vals[6:8]) == "(5.0, 7.0)"
    assert vals[7 + 1] == "us-east-1"
    assert vals[-1] == "True"


def test_production_flag():
    assert settings_for(TEST_ENV="mymetapix")[5] == "True"
