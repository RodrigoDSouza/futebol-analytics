from typing import Any

import pytest

from futebol_analytics.services.campeonatos import (
    CampeonatoNaoEncontradoError,
    localizar_brasileirao_serie_a,
)


class FakeChampionshipProvider:
    def __init__(self, campeonatos: list[dict[str, Any]]) -> None:
        self.campeonatos = campeonatos
        self.received_season: str | None = None
        self.received_type: str | None = None

    def listar_campeonatos(
        self,
        *,
        temporada: str | None = None,
        status: str | None = None,
        tipo: str | None = None,
    ) -> list[dict[str, Any]]:
        self.received_season = temporada
        self.received_type = tipo
        return self.campeonatos


def test_localiza_brasileirao_sem_fixar_id() -> None:
    provider = FakeChampionshipProvider(
        [
            {"id": 62, "nome": "Copa do Brasil", "temporada": "2026"},
            {"id": 3, "nome": "Brasileirão Série A", "temporada": "2026"},
        ]
    )

    campeonato = localizar_brasileirao_serie_a(provider)

    assert campeonato["id"] == 3
    assert provider.received_season == "2026"
    assert provider.received_type == "pontos-corridos"


def test_informa_quando_brasileirao_nao_for_retornado() -> None:
    provider = FakeChampionshipProvider([])

    with pytest.raises(CampeonatoNaoEncontradoError, match="2026"):
        localizar_brasileirao_serie_a(provider)
