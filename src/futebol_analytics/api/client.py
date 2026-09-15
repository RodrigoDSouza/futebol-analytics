"""Único módulo que faz chamadas HTTP da aplicação."""

from types import TracebackType
from typing import Any, Self
import unicodedata

import httpx

from futebol_analytics.api.exceptions import (
    APIConnectionError, APIHTTPError, APIResponseError, DadosFutebolError,
)
from futebol_analytics.config.settings import Settings

JSONObject = dict[str, Any]


def _positive(value: int) -> int:
    if type(value) is not int or value < 1:
        raise ValueError("IDs e números de página devem ser inteiros positivos.")
    return value


def _normalize(value: str) -> str:
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", value.casefold())
                            if not unicodedata.combining(c)).split())


class DadosFutebolClient:
    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None) -> None:
        self._http = httpx.Client(
            base_url=settings.base_url.rstrip("/") + "/v1/",
            headers={"Authorization": f"Bearer {settings.api_key}", "Accept": "application/json"},
            timeout=settings.timeout, follow_redirects=False, transport=transport,
        )
        self.rate_limit: dict[str, str] = {}

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: type[BaseException] | None,
                 exc_value: BaseException | None, traceback: TracebackType | None) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str, params: dict[str, str | int] | None = None) -> JSONObject:
        try:
            response = self._http.get(path, params=params)
        except httpx.TimeoutException:
            raise APIConnectionError("A API excedeu o tempo limite de resposta.") from None
        except httpx.RequestError:
            raise APIConnectionError("Não foi possível conectar à API.") from None
        self.rate_limit = {name: response.headers[name] for name in
                           ("X-RateLimit-Limit", "X-RateLimit-Remaining") if name in response.headers}
        if not response.is_success:
            raise APIHTTPError(response.status_code)
        try:
            payload = response.json()
        except ValueError:
            raise APIResponseError("A API retornou JSON inválido.") from None
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), (dict, list)):
            raise APIResponseError("A resposta não contém o envelope data esperado.")
        return payload

    def _page(self, path: str, pagina: int, por_pagina: int,
              filters: dict[str, str | int | None]) -> JSONObject:
        _positive(pagina)
        if type(por_pagina) is not int or not 1 <= por_pagina <= 100:
            raise ValueError("por_pagina deve estar entre 1 e 100.")
        params = {key: value for key, value in filters.items() if value is not None}
        payload = self._get(path, {**params, "pagina": pagina, "por_pagina": por_pagina})
        meta = payload.get("meta")
        if (not isinstance(payload["data"], list)
                or not all(isinstance(item, dict) for item in payload["data"])
                or not isinstance(meta, dict)):
            raise APIResponseError("A API retornou uma página com estrutura inconsistente.")
        # Produção também retorna listas completas com apenas meta.total.
        # Preservamos a resposta, sem adicionar campos que o servidor não enviou.
        if "ultima_pagina" not in meta and "pagina_atual" not in meta:
            if (pagina != 1 or type(meta.get("total")) is not int
                    or meta["total"] != len(payload["data"])):
                raise APIResponseError("Lista sem paginação incompleta ou página indisponível.")
            return payload
        if (type(meta.get("ultima_pagina")) is not int
                or meta["ultima_pagina"] < pagina
                or meta.get("pagina_atual") != pagina):
            raise APIResponseError("A API retornou uma página com estrutura inconsistente.")
        return payload

    def validar_api_key(self) -> None:
        """Valida no servidor; não retorna nem imprime o perfil da credencial."""
        payload = self._get("me")
        if not isinstance(payload["data"], dict):
            raise APIResponseError("Perfil da API Key inválido na resposta.")

    def listar_campeonatos(self, *, temporada: str = "2026", pagina: int = 1,
                           por_pagina: int = 100) -> JSONObject:
        return self._page("campeonatos", pagina, por_pagina, {"temporada": temporada})

    def localizar_brasileirao(self, temporada: str = "2026") -> JSONObject:
        matches: list[JSONObject] = []
        pagina = 1
        while True:
            payload = self.listar_campeonatos(temporada=temporada, pagina=pagina)
            for item in payload["data"]:
                if (_normalize(str(item.get("nome", ""))) == "brasileirao serie a"
                        and str(item.get("temporada")) == temporada):
                    if type(item.get("id")) is not int or item["id"] < 1:
                        raise APIResponseError("Campeonato encontrado sem ID válido.")
                    matches.append(item)
            if pagina == payload["meta"].get("ultima_pagina", 1):
                break
            pagina += 1
            if pagina > 100:
                raise APIResponseError("Busca interrompida: paginação excessiva ou inconsistente.")
        if len(matches) != 1:
            raise DadosFutebolError("Série A não encontrada de forma única na temporada e no acesso disponíveis.")
        return matches[0]

    def listar_partidas(self, campeonato_id: int, *, pagina: int = 1, por_pagina: int = 15,
                        rodada: int | None = None, status: str | None = None,
                        time_id: int | None = None, data_inicio: str | None = None,
                        data_fim: str | None = None) -> JSONObject:
        return self._page(f"campeonatos/{_positive(campeonato_id)}/partidas", pagina, por_pagina,
                          {"rodada": rodada, "status": status, "time_id": time_id,
                           "data_inicio": data_inicio, "data_fim": data_fim})

    def consultar_tabela(self, campeonato_id: int) -> JSONObject:
        return self._get(f"campeonatos/{_positive(campeonato_id)}/tabela")

    def consultar_estatisticas(self, partida_id: int) -> JSONObject:
        """Preserva campos ausentes/null; não inventa nem calcula métricas."""
        return self._get(f"partidas/{_positive(partida_id)}/estatisticas")

    def consultar_rodadas(self, campeonato_id: int) -> JSONObject:
        """Rodadas e jogos disponibilizados pelo endpoint permitido no plano Free."""
        return self._get(f"campeonatos/{_positive(campeonato_id)}/rodadas")

    def consultar_artilharia(self, campeonato_id: int) -> JSONObject:
        return self._get(f"campeonatos/{_positive(campeonato_id)}/artilharia")
