from futebol_analytics.analysis.round_radar import gerar_radar_rodada


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
        "time_mandante": {"id": mandante, "nome": f"Time {mandante}"},
        "time_visitante": {"id": visitante, "nome": f"Time {visitante}"},
        "placar_mandante": gols_mandante,
        "placar_visitante": gols_visitante,
    }


def test_prioriza_sinal_com_frequencia_e_amostra_completas() -> None:
    encerradas = [
        jogo(f"2026-08-0{indice}T20:00:00-03:00", 1, 10 + indice, 2, 1)
        for indice in range(1, 6)
    ]
    encerradas += [
        jogo(f"2026-08-{10 + indice}T20:00:00-03:00", 20 + indice, 2, 1, 2)
        for indice in range(1, 6)
    ]
    futura = {
        "status": "aguardando",
        "data_realizacao": "10/09/2026",
        "time_mandante": {"id": 1, "nome": "Azul"},
        "time_visitante": {"id": 2, "nome": "Verde"},
    }

    radar = gerar_radar_rodada(
        [{"partidas": encerradas}],
        [futura],
        quantidade=5,
    )

    assert radar[0]["partida"] == "Azul x Verde"
    assert radar[0]["frequencia_historica"] == 100.0
    assert radar[0]["pontuacao"] == 100.0
    assert radar[0]["confianca"] == "Alta"
    assert radar[0]["jogos_analisados"] == 10


def test_ignora_partida_sem_historico_suficiente() -> None:
    futura = {
        "time_mandante": {"id": 1, "nome": "Azul"},
        "time_visitante": {"id": 2, "nome": "Verde"},
    }

    assert gerar_radar_rodada([], [futura]) == []
