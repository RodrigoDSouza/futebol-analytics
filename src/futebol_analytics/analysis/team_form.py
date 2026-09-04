"""Análise da forma recente de um time."""

from typing import Any, Literal


Mando = Literal["todos", "mandante", "visitante"]


class SemPartidasEncerradasError(LookupError):
    """Indica ausência de partidas válidas para a análise solicitada."""


def analisar_forma_time(
    rodadas: list[dict[str, Any]],
    *,
    time_id: int,
    quantidade: int = 5,
    mando: Mando = "todos",
) -> dict[str, Any]:
    """Calcula métricas dos jogos encerrados mais recentes de um time."""
    if time_id <= 0:
        raise ValueError("time_id deve ser um inteiro positivo.")
    if quantidade <= 0:
        raise ValueError("quantidade deve ser um inteiro positivo.")
    if mando not in ("todos", "mandante", "visitante"):
        raise ValueError("mando deve ser 'todos', 'mandante' ou 'visitante'.")

    partidas = _partidas_encerradas_do_time(
        rodadas,
        time_id=time_id,
        mando=mando,
    )
    partidas.sort(
        key=lambda partida: partida.get("data_hora_realizacao") or "",
        reverse=True,
    )
    partidas = partidas[:quantidade]

    if not partidas:
        raise SemPartidasEncerradasError(
            f"Nenhuma partida encerrada foi encontrada para o time {time_id}."
        )

    resultados: list[str] = []
    gols_marcados = 0
    gols_sofridos = 0
    over_15 = 0
    over_25 = 0
    ambas_marcam = 0
    clean_sheets = 0
    partidas_consideradas: list[dict[str, Any]] = []

    for partida in partidas:
        mandante = partida["time_mandante"]
        time_eh_mandante = mandante["id"] == time_id
        gols_time = (
            partida["placar_mandante"]
            if time_eh_mandante
            else partida["placar_visitante"]
        )
        gols_adversario = (
            partida["placar_visitante"]
            if time_eh_mandante
            else partida["placar_mandante"]
        )

        gols_marcados += gols_time
        gols_sofridos += gols_adversario
        total_gols = gols_time + gols_adversario
        over_15 += total_gols > 1
        over_25 += total_gols > 2
        ambas_marcam += gols_time > 0 and gols_adversario > 0
        clean_sheets += gols_adversario == 0

        if gols_time > gols_adversario:
            resultados.append("V")
        elif gols_time == gols_adversario:
            resultados.append("E")
        else:
            resultados.append("D")

        partidas_consideradas.append(
            {
                "data": partida.get("data_realizacao"),
                "data_hora": partida.get("data_hora_realizacao"),
                "mandante": mandante.get("nome") or f"Time {mandante.get('id')}",
                "visitante": partida["time_visitante"].get("nome")
                or f"Time {partida['time_visitante'].get('id')}",
                "placar": f"{partida['placar_mandante']} × {partida['placar_visitante']}",
                "resultado_time": resultados[-1],
            }
        )

    total = len(partidas)
    return {
        "time_id": time_id,
        "mando": mando,
        "jogos_solicitados": quantidade,
        "jogos_analisados": total,
        "vitorias": resultados.count("V"),
        "empates": resultados.count("E"),
        "derrotas": resultados.count("D"),
        "gols_marcados": gols_marcados,
        "gols_sofridos": gols_sofridos,
        "media_gols_marcados": round(gols_marcados / total, 2),
        "media_gols_sofridos": round(gols_sofridos / total, 2),
        "over_1_5": _ocorrencia(over_15, total),
        "over_2_5": _ocorrencia(over_25, total),
        "ambas_marcam": _ocorrencia(ambas_marcam, total),
        "clean_sheets": _ocorrencia(clean_sheets, total),
        "sequencia_recente": resultados,
        "partidas_consideradas": partidas_consideradas,
    }


def _partidas_encerradas_do_time(
    rodadas: list[dict[str, Any]], *, time_id: int, mando: Mando
) -> list[dict[str, Any]]:
    partidas_validas = []

    for rodada in rodadas:
        for partida in rodada.get("partidas", []):
            mandante = partida.get("time_mandante") or {}
            visitante = partida.get("time_visitante") or {}
            envolve_time = time_id in (mandante.get("id"), visitante.get("id"))
            atende_mando = (
                mando == "todos"
                or (mando == "mandante" and mandante.get("id") == time_id)
                or (mando == "visitante" and visitante.get("id") == time_id)
            )
            tem_placar = isinstance(partida.get("placar_mandante"), int) and isinstance(
                partida.get("placar_visitante"), int
            )

            if (
                partida.get("status") == "encerrado"
                and envolve_time
                and atende_mando
                and tem_placar
            ):
                partidas_validas.append(partida)

    return partidas_validas


def _ocorrencia(quantidade: int, total: int) -> dict[str, int | float]:
    return {
        "quantidade": quantidade,
        "percentual": round(quantidade / total * 100, 1),
    }
