from futebol_analytics.analysis.head_to_head import analisar_confrontos_diretos


def partida(data: str, mandante: int, visitante: int, placar: tuple[int, int]) -> dict:
    return {
        "data_realizacao": data[:10],
        "data_hora_realizacao": data,
        "status": "encerrado",
        "time_mandante": {"id": mandante, "nome": f"Time {mandante}"},
        "time_visitante": {"id": visitante, "nome": f"Time {visitante}"},
        "placar_mandante": placar[0],
        "placar_visitante": placar[1],
    }


def test_analisa_confrontos_independentemente_do_mando() -> None:
    rodadas = [
        {
            "partidas": [
                partida("2026-01-01T20:00:00-03:00", 1, 2, (2, 1)),
                partida("2026-06-01T20:00:00-03:00", 2, 1, (0, 0)),
                partida("2026-07-01T20:00:00-03:00", 1, 3, (4, 0)),
            ]
        }
    ]

    resultado = analisar_confrontos_diretos(
        rodadas, time_a_id=1, time_b_id=2, quantidade=5
    )

    assert resultado["jogos_analisados"] == 2
    assert resultado["vitorias_time_a"] == 1
    assert resultado["empates"] == 1
    assert resultado["vitorias_time_b"] == 0
    assert resultado["over_1_5_percentual"] == 50.0
    assert resultado["ambas_marcam_percentual"] == 50.0


def test_retorna_percentuais_indisponiveis_sem_confrontos() -> None:
    resultado = analisar_confrontos_diretos(
        [], time_a_id=1, time_b_id=2, quantidade=5
    )

    assert resultado["jogos_analisados"] == 0
    assert resultado["over_1_5_percentual"] is None
