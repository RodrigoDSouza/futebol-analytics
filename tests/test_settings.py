from pathlib import Path

import pytest

import futebol_analytics.config.settings as settings_module
from futebol_analytics.config.settings import ConfigurationError, Settings


def test_settings_from_env_reads_required_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DADOS_FUTEBOL_API_KEY", "chave-de-teste")
    monkeypatch.setenv("DADOS_FUTEBOL_BASE_URL", "https://example.test/")

    settings = Settings.from_env()

    assert settings.api_key == "chave-de-teste"
    assert settings.base_url == "https://example.test"


def test_settings_from_env_rejects_missing_api_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DADOS_FUTEBOL_API_KEY", raising=False)
    monkeypatch.setattr(settings_module, "load_dotenv", lambda: False)

    with pytest.raises(ConfigurationError, match="DADOS_FUTEBOL_API_KEY"):
        Settings.from_env()
