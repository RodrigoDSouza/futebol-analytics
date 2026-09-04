import pytest

from futebol_analytics.analysis.matchup import comparar_mandante_visitante


def jogo(
    data: str,
    mandante: int,
    visitante: int,
    gols_mandante: int,
    gols_visitante: int,
) -> dict:
    return {
        "data_hora_realizacao": data,
        "status": "encerrado",
        "time_mandante": {"id": mandante},
        "time_visitante": {"id": visitante},
        "placar_mandante": gols_mandante,
        "placar_visitante": gols_visitante,
    }


def test_compara_recortes_corretos_de_mando() -> None:
    rodadas = [
        {
            "partidas": [
                jogo("2026-01-01T20:00:00-03:00", 1, 3, 2, 0),
                jogo("2026-01-02T20:00:00-03:00", 4, 2, 1, 1),
                jogo("2026-01-03T20:00:00-03:00", 5, 1, 4, 0),
                jogo("2026-01-04T20:00:00-03:00", 2, 6, 3, 0),
            ]
        }
    ]

    comparacao = comparar_mandante_visitante(
        rodadas,
        mandante_id=1,
        visitante_id=2,
        quantidade=5,
    )

    assert comparacao["mandante"]["mando"] == "mandante"
    assert comparacao["mandante"]["vitorias"] == 1
    assert comparacao["visitante"]["mando"] == "visitante"
    assert comparacao["visitante"]["empates"] == 1
    assert comparacao["resumo_combinado"]["over_1_5_percentual_medio"] == 100.0


def test_rejeita_comparacao_do_time_com_ele_mesmo() -> None:
    with pytest.raises(ValueError, match="diferentes"):
        comparar_mandante_visitante([], mandante_id=1, visitante_id=1)

