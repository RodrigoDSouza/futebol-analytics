"""Cliente centralizado para a API Dados Futebol."""

from typing import Any, Self

import httpx

from futebol_analytics.api.exceptions import (
    DadosFutebolConnectionError,
    DadosFutebolResponseError,
)
from futebol_analytics.config.settings import Settings


class DadosFutebolClient:
    """Realiza requisições autenticadas à API Dados Futebol."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=settings.base_url,
            headers={
                "Authorization": f"Bearer {settings.api_key}",
                "Accept": "application/json",
            },
            timeout=settings.timeout_seconds,
            transport=transport,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        """Libera as conexões mantidas pelo cliente HTTP."""
        self._client.close()

    def consultar_perfil(self) -> dict[str, Any]:
        """Valida a chave e devolve os dados do seu perfil e consumo."""
        return self._get_data("/v1/me")

    def listar_campeonatos(
        self,
        *,
        temporada: str | None = None,
        status: str | None = None,
        tipo: str | None = None,
    ) -> list[dict[str, Any]]:
        """Lista campeonatos, aplicando somente filtros documentados."""
        params = {
            key: value
            for key, value in {
                "temporada": temporada,
                "status": status,
                "tipo": tipo,
            }.items()
            if value is not None
        }
        data = self._get_data("/v1/campeonatos", params=params)

        if not isinstance(data, list):
            raise DadosFutebolResponseError(
                "A API retornou um formato inesperado para campeonatos."
            )
        return data

    def consultar_rodadas(self, campeonato_id: int) -> list[dict[str, Any]]:
        """Retorna as rodadas e respectivas partidas de um campeonato."""
        self._validar_id(campeonato_id, "campeonato_id")
        data = self._get_data(f"/v1/campeonatos/{campeonato_id}/rodadas")

        if not isinstance(data, list):
            raise DadosFutebolResponseError(
                "A API retornou um formato inesperado para rodadas."
            )
        return data

    def consultar_tabela(self, campeonato_id: int) -> dict[str, Any]:
        """Retorna a tabela de classificação de um campeonato."""
        self._validar_id(campeonato_id, "campeonato_id")
        data = self._get_data(f"/v1/campeonatos/{campeonato_id}/tabela")

        if not isinstance(data, dict):
            raise DadosFutebolResponseError(
                "A API retornou um formato inesperado para a tabela."
            )
        return data

    @staticmethod
    def _validar_id(resource_id: int, parameter_name: str) -> None:
        if resource_id <= 0:
            raise ValueError(f"{parameter_name} deve ser um inteiro positivo.")

    def _get_data(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
    ) -> Any:
        try:
            response = self._client.get(path, params=params)
        except httpx.RequestError as exc:
            raise DadosFutebolConnectionError(
                "Não foi possível conectar à API Dados Futebol."
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise DadosFutebolResponseError(
                "A API retornou uma resposta que não é um JSON válido.",
                status_code=response.status_code,
            ) from exc

        if response.is_error:
            message = (
                payload.get("mensagem", "A API retornou um erro sem mensagem.")
                if isinstance(payload, dict)
                else "A API retornou um erro sem mensagem."
            )
            raise DadosFutebolResponseError(
                message,
                status_code=response.status_code,
            )

        if not isinstance(payload, dict) or "data" not in payload:
            raise DadosFutebolResponseError(
                "A resposta da API não contém o campo 'data'.",
                status_code=response.status_code,
            )

        return payload["data"]
