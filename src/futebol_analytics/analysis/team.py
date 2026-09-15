"""Métricas históricas e critérios explícitos de seleção da amostra."""

from collections import Counter
from typing import Any


def analyze_team(matches: list[dict[str, Any]], team_id: int, *, last: int | None = None,
                 venue: str = "todos", opponent_id: int | None = None) -> dict[str, Any]:
    if last not in (None, 5, 10) or venue not in ("todos", "mandante", "visitante"):
        raise ValueError("Use últimos 5/10 e mando todos/mandante/visitante.")
    selected = []
    for match in matches:
        if team_id not in (match["mandante_id"], match["visitante_id"]):
            continue
        home = match["mandante_id"] == team_id
        if venue == "mandante" and not home or venue == "visitante" and home:
            continue
        opponent = match["visitante_id"] if home else match["mandante_id"]
        if opponent_id is not None and opponent != opponent_id:
            continue
        selected.append(match)
    eligible, rejected = [], []
    for match in selected:
        reason = None
        if match["status"] != "encerrado":
            reason = "nao_encerrado"
        elif any(type(match[field]) is not int or match[field] < 0
                 for field in ("placar_mandante", "placar_visitante")):
            reason = "placar_incompleto_ou_invalido"
        elif match["data_hora"] is not None and match["data_hora"] > match["coletado_em"]:
            reason = "data_posterior_a_coleta"
        elif last is not None and match["data_hora"] is None:
            reason = "sem_data_para_sequencia"
        if reason:
            rejected.append({"partida_id": match["id"], "motivo": reason})
        else:
            eligible.append(match)
    if last is not None:
        eligible.sort(key=lambda m: (m["data_hora"], m["id"]), reverse=True)
        used, outside = eligible[:last], eligible[last:]
    else:
        used, outside = eligible, []
    outcomes = []
    for match in used:
        home = match["mandante_id"] == team_id
        scored = match["placar_mandante"] if home else match["placar_visitante"]
        conceded = match["placar_visitante"] if home else match["placar_mandante"]
        outcomes.append(dict(partida_id=match["id"], data_hora=match["data_hora"],
                             mando="mandante" if home else "visitante", gols_pro=scored,
                             gols_contra=conceded, resultado="V" if scored > conceded else "E" if scored == conceded else "D",
                             captura_id=str(match["captura_id"])))
    n = len(outcomes)
    results = Counter(o["resultado"] for o in outcomes)
    goals_for = sum(o["gols_pro"] for o in outcomes)
    goals_against = sum(o["gols_contra"] for o in outcomes)

    def frequency(count: int) -> dict[str, int | float | None]:
        return {"ocorrencias": count, "jogos": n, "percentual": round(100 * count / n, 2) if n else None}

    frequencies = {
        f"over_{threshold}": frequency(sum(o["gols_pro"] + o["gols_contra"] > threshold for o in outcomes))
        for threshold in (0.5, 1.5, 2.5, 3.5)
    }
    frequencies["ambas_marcam"] = frequency(sum(o["gols_pro"] > 0 and o["gols_contra"] > 0 for o in outcomes))
    frequencies["sem_sofrer_gols"] = frequency(sum(o["gols_contra"] == 0 for o in outcomes))
    # A forma só é apresentada quando toda a amostra usada pode ser ordenada.
    dated = all(o["data_hora"] is not None for o in outcomes)
    chronological = sorted(outcomes, key=lambda o: (o["data_hora"], o["partida_id"])) if dated else []
    return {
        "metodologia": "estatistica_descritiva_v1",
        "filtros": {"time_id": team_id, "ultimos_validos": last, "mando": venue, "adversario_id": opponent_id},
        "amostra": {"encontrados_no_recorte": len(selected), "elegiveis": len(eligible), "utilizados": n,
                    "excluidos_por_criterio": len(rejected), "fora_da_janela": len(outside),
                    "motivos_exclusao": dict(Counter(r["motivo"] for r in rejected)),
                    "utilizados_sem_data": sum(o["data_hora"] is None for o in outcomes),
                    "janela_completa": n == last if last is not None else None},
        "resultados": {"vitorias": results["V"], "empates": results["E"], "derrotas": results["D"]},
        "gols": {"marcados": goals_for, "sofridos": goals_against,
                 "media_marcados": round(goals_for / n, 4) if n else None,
                 "media_sofridos": round(goals_against / n, 4) if n else None,
                 "media_total_por_jogo": round((goals_for + goals_against) / n, 4) if n else None},
        "frequencias_historicas": frequencies,
        "forma_do_mais_antigo_ao_mais_recente": [o["resultado"] for o in chronological] if dated else None,
        "jogos_utilizados": outcomes, "jogos_excluidos": rejected,
        "ids_fora_da_janela": [m["id"] for m in outside],
        "limites": "Frequências da amostra local, não probabilidades futuras. Últimos significa últimos jogos válidos disponíveis; não é backtesting.",
    }
