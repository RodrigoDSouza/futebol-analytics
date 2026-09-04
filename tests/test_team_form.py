import pytest

from futebol_analytics.analysis.team_form import (
    SemPartidasEncerradasError,
    analisar_forma_time,
)


def partida(
    *,
    data: str,
    mandante_id: int,
    visitante_id: int,
    placar_mandante: int | None,
    placar_visitante: int | None,
    status: str = "encerrado",
) -> dict:
    return {
        "data_hora_realizacao": data,
        "status": status,
        "time_mandante": {"id": mandante_id},
        "time_visitante": {"id": visitante_id},
        "placar_mandante": placar_mandante,
        "placar_visitante": placar_visitante,
    }


def test_analisa_resultados_do_ponto_de_vista_do_time() -> None:
    rodadas = [
        {
            "partidas": [
                partida(
                    data="2026-04-01T20:00:00-03:00",
                    mandante_id=1,
                    visitante_id=2,
                    placar_mandante=2,
                    placar_visitante=0,
                ),
                partida(
                    data="2026-04-08T20:00:00-03:00",
                    mandante_id=3,
                    visitante_id=1,
                    placar_mandante=1,
                    placar_visitante=1,
                ),
                partida(
                    data="2026-04-15T20:00:00-03:00",
                    mandante_id=1,
                    visitante_id=4,
                    placar_mandante=1,
                    placar_visitante=3,
                ),
            ]
        }
    ]

    resultado = analisar_forma_time(rodadas, time_id=1, quantidade=3)

    assert resultado["sequencia_recente"] == ["D", "E", "V"]
    assert resultado["vitorias"] == 1
    assert resultado["empates"] == 1
    assert resultado["derrotas"] == 1
    assert resultado["gols_marcados"] == 4
    assert resultado["gols_sofridos"] == 4
    assert resultado["media_gols_marcados"] == 1.33
    assert resultado["over_1_5"] == {"quantidade": 3, "percentual": 100.0}
    assert resultado["over_2_5"] == {"quantidade": 1, "percentual": 33.3}
    assert resultado["ambas_marcam"] == {"quantidade": 2, "percentual": 66.7}
    assert resultado["clean_sheets"] == {"quantidade": 1, "percentual": 33.3}


def test_ignora_jogos_nao_encerrados_ou_sem_placar() -> None:
    rodadas = [
        {
            "partidas": [
                partida(
                    data="2026-05-01T20:00:00-03:00",
                    mandante_id=1,
                    visitante_id=2,
                    placar_mandante=None,
                    placar_visitante=None,
                    status="aguardando",
                )
            ]
        }
    ]

    with pytest.raises(SemPartidasEncerradasError):
        analisar_forma_time(rodadas, time_id=1)


def test_limita_a_quantidade_de_jogos_mais_recentes() -> None:
    jogos = [
        partida(
            data=f"2026-04-{dia:02d}T20:00:00-03:00",
            mandante_id=1,
            visitante_id=2,
            placar_mandante=1,
            placar_visitante=0,
        )
        for dia in range(1, 8)
    ]

    resultado = analisar_forma_time([{"partidas": jogos}], time_id=1, quantidade=5)

    assert resultado["jogos_analisados"] == 5
    assert resultado["vitorias"] == 5


def test_filtra_jogos_em_que_time_foi_mandante() -> None:
    jogos = [
        partida(
            data="2026-06-01T20:00:00-03:00",
            mandante_id=1,
            visitante_id=2,
            placar_mandante=2,
            placar_visitante=0,
        ),
        partida(
            data="2026-06-08T20:00:00-03:00",
            mandante_id=3,
            visitante_id=1,
            placar_mandante=3,
            placar_visitante=0,
        ),
    ]

    resultado = analisar_forma_time(
        [{"partidas": jogos}],
        time_id=1,
        mando="mandante",
    )

    assert resultado["mando"] == "mandante"
    assert resultado["jogos_analisados"] == 1
    assert resultado["vitorias"] == 1


def test_filtra_jogos_em_que_time_foi_visitante() -> None:
    jogos = [
        partida(
            data="2026-06-01T20:00:00-03:00",
            mandante_id=1,
            visitante_id=2,
            placar_mandante=2,
            placar_visitante=0,
        ),
        partida(
            data="2026-06-08T20:00:00-03:00",
            mandante_id=3,
            visitante_id=1,
            placar_mandante=3,
            placar_visitante=0,
        ),
    ]

    resultado = analisar_forma_time(
        [{"partidas": jogos}],
        time_id=1,
        mando="visitante",
    )

    assert resultado["mando"] == "visitante"
    assert resultado["jogos_analisados"] == 1
    assert resultado["derrotas"] == 1


def test_rejeita_mando_desconhecido() -> None:
    with pytest.raises(ValueError, match="mando"):
        analisar_forma_time([], time_id=1, mando="neutro")  # type: ignore[arg-type]
