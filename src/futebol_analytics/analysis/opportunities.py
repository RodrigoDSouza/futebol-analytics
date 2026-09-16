"""Ranking experimental de mercados, com abstenção e validação cronológica."""

from __future__ import annotations

from datetime import date
import math
import re
import unicodedata
from typing import Any

from futebol_analytics.models.poisson import markets


MIN_LEAGUE = 30
MIN_VENUE = 5
PRIOR_MATCHES = 5
MIN_BACKTEST = 30
MIN_EDGE = 0.03
MIN_EV = 0.03


def _name(value: str) -> str:
    text = "".join(char for char in unicodedata.normalize("NFKD", value.casefold())
                   if not unicodedata.combining(char))
    words = re.findall(r"[a-z0-9]+", text)
    ignored = {"fc", "afc", "cf", "sc", "ec", "club", "clube", "football", "futebol"}
    return " ".join(word for word in words if word not in ignored)


def resolve_team(team: str, candidates: set[str]) -> str | None:
    """Resolve apenas nomes inequívocos, evitando associar equipes por palpite."""
    wanted = _name(team)
    exact = [candidate for candidate in candidates if _name(candidate) == wanted]
    if len(exact) == 1:
        return exact[0]
    contained = [candidate for candidate in candidates
                 if wanted and (_name(candidate) in wanted or wanted in _name(candidate))]
    return contained[0] if len(contained) == 1 else None


def predict_match(rows: list[dict[str, Any]], home: str, away: str,
                  cutoff: date) -> dict[str, Any]:
    """Estima o confronto com forças por mando regularizadas pela média da liga."""
    valid = [row for row in rows if date.fromisoformat(str(row["data"])) < cutoff
             and all(type(row.get(key)) is int and row[key] >= 0
                     for key in ("gols_mandante", "gols_visitante"))]
    candidates = {str(row[key]) for row in valid for key in ("mandante", "visitante")}
    local_home, local_away = resolve_team(home, candidates), resolve_team(away, candidates)
    if local_home is None or local_away is None or local_home == local_away:
        raise ValueError("Não foi possível associar as equipes ao histórico de forma inequívoca.")
    home_rows = sorted((row for row in valid if row["mandante"] == local_home),
                       key=lambda row: str(row["data"]), reverse=True)[:10]
    away_rows = sorted((row for row in valid if row["visitante"] == local_away),
                       key=lambda row: str(row["data"]), reverse=True)[:10]
    if len(valid) < MIN_LEAGUE or len(home_rows) < MIN_VENUE or len(away_rows) < MIN_VENUE:
        raise ValueError("Amostra insuficiente para este confronto.")

    league_home = sum(row["gols_mandante"] for row in valid) / len(valid)
    league_away = sum(row["gols_visitante"] for row in valid) / len(valid)
    if league_home <= 0 or league_away <= 0:
        raise ValueError("Média de gols inválida no histórico.")

    def shrunk(sample: list[dict[str, Any]], field: str, prior: float) -> float:
        return (sum(row[field] for row in sample) + PRIOR_MATCHES * prior) / (len(sample) + PRIOR_MATCHES)

    home_scored = shrunk(home_rows, "gols_mandante", league_home)
    home_allowed = shrunk(home_rows, "gols_visitante", league_away)
    away_scored = shrunk(away_rows, "gols_visitante", league_away)
    away_allowed = shrunk(away_rows, "gols_mandante", league_home)
    lambda_home = league_home * (home_scored / league_home) * (away_allowed / league_home)
    lambda_away = league_away * (away_scored / league_away) * (home_allowed / league_away)
    result = markets(lambda_home, lambda_away)
    return {
        "modelo": "poisson_mando_regularizado_v1",
        "equipes_historico": {"mandante": local_home, "visitante": local_away},
        "amostra": {"liga": len(valid), "mandante_casa": len(home_rows),
                    "visitante_fora": len(away_rows), "peso_prior": PRIOR_MATCHES},
        "gols_esperados": {"mandante": lambda_home, "visitante": lambda_away},
        **result,
    }


def validate(rows: list[dict[str, Any]], market: str) -> dict[str, Any]:
    """Walk-forward: cada previsão enxerga exclusivamente datas anteriores."""
    supported = {"over_1.5", "over_2.5", "ambas_marcam"}
    if market not in supported:
        raise ValueError("Mercado sem validação binária.")
    ordered = sorted(rows, key=lambda row: (str(row["data"]), row["mandante"], row["visitante"]))
    predictions = []
    for target in ordered:
        if not all(type(target.get(key)) is int and target[key] >= 0
                   for key in ("gols_mandante", "gols_visitante")):
            continue
        cutoff = date.fromisoformat(str(target["data"]))
        try:
            probability = predict_match(ordered, target["mandante"], target["visitante"], cutoff)[
                "probabilidades"][market]
        except ValueError:
            continue
        history = [row for row in ordered if date.fromisoformat(str(row["data"])) < cutoff]
        if market == "ambas_marcam":
            occurred = lambda row: row["gols_mandante"] > 0 and row["gols_visitante"] > 0
        else:
            threshold = 2 if market == "over_1.5" else 3
            occurred = lambda row: row["gols_mandante"] + row["gols_visitante"] >= threshold
        baseline = (1 + sum(occurred(row) for row in history)) / (len(history) + 2)
        predictions.append((probability, baseline, int(occurred(target))))
    count = len(predictions)
    brier = (sum((p - result) ** 2 for p, _, result in predictions) / count
             if count else None)
    baseline_brier = (sum((base - result) ** 2 for _, base, result in predictions) / count
                      if count else None)
    approved = bool(count >= MIN_BACKTEST and brier is not None and brier < baseline_brier)
    return {"mercado": market, "jogos_avaliados": count, "brier_modelo": brier,
            "brier_liga": baseline_brier, "aprovado": approved,
            "criterio": f"mínimo {MIN_BACKTEST} jogos e Brier do modelo menor que o da liga"}


def rank_opportunities(rows: list[dict[str, Any]], odds: list[dict[str, Any]],
                       *, today: date) -> dict[str, Any]:
    """Cruza previsões e consensos; mercados reprovados ou fracos são omitidos."""
    mappings = {
        ("totals", "Over", 1.5): ("over_1.5", False, "Mais de 1,5 gols"),
        ("totals", "Under", 1.5): ("over_1.5", True, "Menos de 1,5 gols"),
        ("alternate_totals", "Over", 1.5): ("over_1.5", False, "Mais de 1,5 gols"),
        ("alternate_totals", "Under", 1.5): ("over_1.5", True, "Menos de 1,5 gols"),
        ("totals", "Over", 2.5): ("over_2.5", False, "Mais de 2,5 gols"),
        ("totals", "Under", 2.5): ("over_2.5", True, "Menos de 2,5 gols"),
        ("btts", "Yes", 0.0): ("ambas_marcam", False, "Ambos marcam · Sim"),
        ("btts", "No", 0.0): ("ambas_marcam", True, "Ambos marcam · Não"),
    }
    validations = {key: validate(rows, key) for key in {value[0] for value in mappings.values()}}
    predictions: dict[str, dict[str, Any]] = {}
    rejected: dict[str, str] = {}
    candidates = []
    for quote in odds:
        event_id = str(quote["evento_id"])
        if event_id not in predictions and event_id not in rejected:
            try:
                predictions[event_id] = predict_match(
                    rows, quote["mandante"], quote["visitante"], today)
            except ValueError as error:
                rejected[event_id] = str(error)
        mapping = mappings.get((quote["mercado"], quote["selecao"], float(quote["linha"] or 0)))
        if not mapping or event_id not in predictions:
            continue
        model_market, complement, label = mapping
        probability = predictions[event_id]["probabilidades"][model_market]
        probability = 1 - probability if complement else probability
        fair = quote.get("probabilidade_justa")
        price = quote.get("odd_melhor") or quote.get("odd_mediana")
        edge = probability - fair if fair is not None else None
        expected_value = probability * price - 1 if price is not None else None
        validation = validations[model_market]
        eligible = bool(validation["aprovado"] and quote.get("casas", 0) >= 3
                        and edge is not None and expected_value is not None
                        and edge >= MIN_EDGE and expected_value >= MIN_EV)
        candidates.append({
            "evento_id": event_id, "inicio": quote["inicio"],
            "jogo": f'{quote["mandante"]} × {quote["visitante"]}', "mercado": label,
            "probabilidade_modelo": probability, "probabilidade_mercado": fair,
            "vantagem": edge, "odd_referencia": price, "valor_esperado": expected_value,
            "casas": quote.get("casas", 0), "validacao": validation,
            "gols_esperados": predictions[event_id]["gols_esperados"], "elegivel": eligible,
        })
    ranked = sorted((row for row in candidates if row["elegivel"]),
                    key=lambda row: (-row["valor_esperado"], -row["vantagem"], row["inicio"]))
    # A consulta adicional é cara: prioriza os eventos cuja cotação já disponível
    # mais diverge do modelo, mesmo que o mercado atual ainda não passe nas travas.
    event_scores: dict[str, float] = {}
    for row in candidates:
        if row["vantagem"] is not None:
            event_scores[row["evento_id"]] = max(event_scores.get(row["evento_id"], 0),
                                                  abs(row["vantagem"]))
    shortlist = [event_id for event_id, _ in sorted(event_scores.items(),
                 key=lambda item: (-item[1], item[0]))[:3]]
    return {"modelo": "poisson_mando_regularizado_v1", "oportunidades": ranked,
            "candidatos_avaliados": len(candidates), "eventos_sem_modelo": rejected,
            "pre_selecao_eventos": shortlist,
            "validacoes": validations,
            "criterios": {"minimo_casas": 3, "vantagem_minima": MIN_EDGE,
                          "valor_esperado_minimo": MIN_EV, "mercado_deve_superar_liga": True},
            "aviso": "Ranking experimental; odds mudam e desempenho histórico não garante retorno futuro."}
