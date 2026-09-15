"""Carrega configuração local sem incluir segredos na representação do objeto."""

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values


class ConfigurationError(ValueError):
    """Configuração ausente ou inválida."""


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    base_url: str = "https://api.dadosfutebol.com.br"
    timeout: float = 20.0

    def __post_init__(self) -> None:
        if not self.api_key or any(c.isspace() for c in self.api_key) or not self.api_key.isascii():
            raise ConfigurationError("Defina uma API Key válida em DADOS_FUTEBOL_API_KEY no .env.")
        url = urlsplit(self.base_url)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.path not in ("", "/")):
            raise ConfigurationError("DADOS_FUTEBOL_BASE_URL deve ser uma origem HTTPS, sem /v1.")
        if not math.isfinite(self.timeout) or self.timeout <= 0:
            raise ConfigurationError("DADOS_FUTEBOL_TIMEOUT deve ser positivo e finito.")


def load_settings(env_file: Path = Path(".env")) -> Settings:
    """O ambiente do processo tem precedência sobre o arquivo da pasta atual."""
    values = {**dotenv_values(env_file, interpolate=False), **os.environ}
    try:
        timeout = float(values.get("DADOS_FUTEBOL_TIMEOUT", "20"))
    except (TypeError, ValueError):
        raise ConfigurationError("DADOS_FUTEBOL_TIMEOUT deve ser um número.") from None
    return Settings(
        api_key=(values.get("DADOS_FUTEBOL_API_KEY") or "").strip(),
        base_url=(values.get("DADOS_FUTEBOL_BASE_URL") or "https://api.dadosfutebol.com.br").strip(),
        timeout=timeout,
    )


@dataclass(frozen=True)
class DatabaseSettings:
    url: str = field(repr=False)

    def __post_init__(self) -> None:
        try:
            parsed = urlsplit(self.url)
            valid = (parsed.scheme in ("postgresql", "postgres") and parsed.hostname
                     and parsed.path not in ("", "/") and not parsed.fragment)
            parsed.port
        except ValueError:
            valid = False
        if not valid:
            raise ConfigurationError("Defina FUTEBOL_DATABASE_URL com uma URL PostgreSQL válida no .env.")


def load_database_settings(env_file: Path = Path(".env")) -> DatabaseSettings:
    """Comandos locais não exigem credenciais da API."""
    values = {**dotenv_values(env_file, interpolate=False), **os.environ}
    return DatabaseSettings(url=(values.get("FUTEBOL_DATABASE_URL") or "").strip())
