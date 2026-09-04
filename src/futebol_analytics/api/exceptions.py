"""Exceções específicas da integração com a API Dados Futebol."""


class DadosFutebolError(Exception):
    """Classe base para erros da integração."""


class DadosFutebolConnectionError(DadosFutebolError):
    """Indica falha de rede ao acessar a API."""


class DadosFutebolResponseError(DadosFutebolError):
    """Indica uma resposta HTTP de erro ou um JSON inesperado."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

