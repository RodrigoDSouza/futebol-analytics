"""Casos de uso relacionados a campeonatos."""

from typing import Any, Protocol
import unicodedata


class ChampionshipProvider(Protocol):
    """Contrato mínimo de quem fornece campeonatos ao serviço."""

    def listar_campeonatos(
        self,
        *,
        temporada: str | None = None,
        status: str | None = None,
        tipo: str | None = None,
    ) -> list[dict[str, Any]]: ...


class CampeonatoNaoEncontradoError(LookupError):
    """Indica que o campeonato procurado não foi retornado pela API."""


def localizar_brasileirao_serie_a(
    provider: ChampionshipProvider,
    *,
    temporada: str = "2026",
) -> dict[str, Any]:
    """Localiza dinamicamente o Brasileirão Série A de uma temporada."""
    campeonatos = provider.listar_campeonatos(
        temporada=temporada,
        tipo="pontos-corridos",
    )

    for campeonato in campeonatos:
        nome = campeonato.get("nome")
        if isinstance(nome, str) and _normalizar(nome) == "brasileirao serie a":
            return campeonato

    raise CampeonatoNaoEncontradoError(
        f"Brasileirão Série A da temporada {temporada} não foi encontrado."
    )


def _normalizar(texto: str) -> str:
    sem_acentos = "".join(
        caractere
        for caractere in unicodedata.normalize("NFD", texto)
        if unicodedata.category(caractere) != "Mn"
    )
    return " ".join(sem_acentos.casefold().split())

