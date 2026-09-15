"""Erros públicos; mensagens não contêm headers nem corpos de resposta."""


class DadosFutebolError(Exception):
    """Falha de integração ou de seleção dos dados."""


class APIHTTPError(DadosFutebolError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        messages = {
            401: "API Key inválida ou inativa.",
            403: "Seu plano não permite acessar este recurso.",
            404: "Recurso não encontrado ou dados ainda indisponíveis.",
            422: "A API rejeitou os parâmetros da consulta.",
            429: "Limite de requisições atingido. Aguarde a renovação da cota.",
        }
        super().__init__(f"HTTP {status_code}: " + messages.get(status_code, "Falha na resposta da API."))


class APIConnectionError(DadosFutebolError):
    """Timeout ou falha de rede."""


class APIResponseError(DadosFutebolError):
    """JSON ou envelope incompatível com o contrato esperado."""
