"""Carregamento e validação das configurações da aplicação."""

from dataclasses import dataclass
import os

from dotenv import load_dotenv


DEFAULT_BASE_URL = "https://api.dadosfutebol.com.br"


class ConfigurationError(ValueError):
    """Indica que uma configuração obrigatória está ausente ou inválida."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Configurações necessárias para acessar a API Dados Futebol."""

    api_key: str
    base_url: str = DEFAULT_BASE_URL
    timeout_seconds: float = 10.0

    @classmethod
    def from_env(cls) -> "Settings":
        """Cria as configurações usando o arquivo .env e o ambiente do processo."""
        load_dotenv()

        api_key = os.getenv("DADOS_FUTEBOL_API_KEY", "").strip()
        base_url = os.getenv("DADOS_FUTEBOL_BASE_URL", DEFAULT_BASE_URL).strip()

        if not api_key:
            raise ConfigurationError(
                "DADOS_FUTEBOL_API_KEY não foi definida. "
                "Copie .env.example para .env e informe sua chave."
            )
        if not base_url.startswith(("http://", "https://")):
            raise ConfigurationError(
                "DADOS_FUTEBOL_BASE_URL deve começar com http:// ou https://."
            )

        return cls(api_key=api_key, base_url=base_url.rstrip("/"))
