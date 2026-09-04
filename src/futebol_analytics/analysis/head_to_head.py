"""Análise de confrontos diretos entre dois times."""

from typing import Any


def analisar_confrontos_diretos(
    rodadas: list[dict[str, Any]],
    *,
    time_a_id: int,
    time_b_id: int,
    quantidade: int = 5,
) -> dict[str, Any]:
    """Resume confrontos encerrados entre dois times no conjunto recebido."""
    if time_a_id == time_b_id:
        raise ValueError("Os times dos confrontos diretos devem ser diferentes.")
    if quantidade <= 0:
        raise ValueError("quantidade deve ser um inteiro positivo.")

    partidas = []
    for rodada in rodadas:
        for partida in rodada.get("partidas", []):
            mandante = partida.get("time_mandante") or {}
            visitante = partida.get("time_visitante") or {}
            participantes = {mandante.get("id"), visitante.get("id")}
            tem_placar = isinstance(partida.get("placar_mandante"), int) and isinstance(
                partida.get("placar_visitante"), int
            )
            if (
                participantes == {time_a_id, time_b_id}
                and partida.get("status") == "encerrado"
                and tem_placar
            ):
                partidas.append(partida)

    partidas.sort(
        key=lambda partida: partida.get("data_hora_realizacao") or "",
        reverse=True,
    )
    partidas = partidas[:quantidade]

    vitorias_a = empates = vitorias_b = over_15 = over_25 = ambas = 0
    detalhes = []
    for partida in partidas:
        a_mandante = partida["time_mandante"]["id"] == time_a_id
        gols_a = partida["placar_mandante"] if a_mandante else partida["placar_visitante"]
        gols_b = partida["placar_visitante"] if a_mandante else partida["placar_mandante"]
        if gols_a > gols_b:
            vitorias_a += 1
        elif gols_a == gols_b:
            empates += 1
        else:
            vitorias_b += 1

        total_gols = gols_a + gols_b
        over_15 += total_gols > 1
        over_25 += total_gols > 2
        ambas += gols_a > 0 and gols_b > 0
        detalhes.append(
            {
                "data": partida.get("data_realizacao"),
                "mandante": partida["time_mandante"].get("nome"),
                "visitante": partida["time_visitante"].get("nome"),
                "placar": f"{partida['placar_mandante']} × {partida['placar_visitante']}",
            }
        )

    total = len(partidas)
    return {
        "jogos_analisados": total,
        "vitorias_time_a": vitorias_a,
        "empates": empates,
        "vitorias_time_b": vitorias_b,
        "over_1_5_percentual": _percentual(over_15, total),
        "over_2_5_percentual": _percentual(over_25, total),
        "ambas_marcam_percentual": _percentual(ambas, total),
        "partidas_consideradas": detalhes,
    }


def _percentual(ocorrencias: int, total: int) -> float | None:
    if total == 0:
        return None
    return round(ocorrencias / total * 100, 1)

