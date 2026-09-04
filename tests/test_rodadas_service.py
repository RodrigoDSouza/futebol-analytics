from datetime import datetime, timezone

import pytest

from futebol_analytics.services.rodadas import (
    ProximaRodadaNaoEncontradaError,
    localizar_proxima_rodada,
)


def rodada(numero: int, data: str | None, *, status: str = "aguardando") -> dict:
    return {
        "numero": numero,
        "partidas": [
            {
                "status": status,
                "data_hora_realizacao": data,
            }
        ],
    }


def test_localiza_rodada_pela_partida_futura_mais_proxima() -> None:
    rodadas = [
        rodada(21, "2026-07-29T20:00:00-03:00"),
        rodada(27, "2026-09-11T20:00:00-03:00"),
        rodada(26, "2026-09-05T20:00:00-03:00"),
    ]

    resultado = localizar_proxima_rodada(
        rodadas,
        agora=datetime(2026, 9, 4, tzinfo=timezone.utc),
    )

    assert resultado["numero"] == 26


def test_ignora_data_ausente_invalida_e_partida_encerrada() -> None:
    rodadas = [
        rodada(1, None),
        rodada(2, "data-inválida"),
        rodada(3, "2026-09-05T20:00:00-03:00", status="encerrado"),
    ]

    with pytest.raises(ProximaRodadaNaoEncontradaError):
        localizar_proxima_rodada(
            rodadas,
            agora=datetime(2026, 9, 4, tzinfo=timezone.utc),
        )
