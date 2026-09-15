from dataclasses import fields

import pytest

from futebol_analytics.config.settings import ConfigurationError, Settings, load_settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in ("API_KEY", "BASE_URL", "TIMEOUT"):
        monkeypatch.delenv(f"DADOS_FUTEBOL_{name}", raising=False)


def test_missing_key(tmp_path):
    with pytest.raises(ConfigurationError, match="API Key"):
        load_settings(tmp_path / "missing.env")


def test_env_file_and_environment_precedence(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("DADOS_FUTEBOL_API_KEY=fixture-only\nDADOS_FUTEBOL_TIMEOUT=12\n", encoding="utf-8")
    monkeypatch.setenv("DADOS_FUTEBOL_TIMEOUT", "7")
    settings = load_settings(path)
    assert settings.timeout == 7
    assert all(not f.repr for f in fields(settings) if f.name == "api_key")


@pytest.mark.parametrize("url", ["http://example.com", "https://example.com/v1", "https://example.com?x=1"])
def test_invalid_base_url(url):
    with pytest.raises(ConfigurationError):
        Settings("fixture-only", base_url=url)


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_invalid_timeout(timeout):
    with pytest.raises(ConfigurationError):
        Settings("fixture-only", timeout=timeout)
