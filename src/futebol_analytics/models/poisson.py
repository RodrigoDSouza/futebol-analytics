"""Poisson independente com forças relativas ao campeonato e ao mando."""

from collections import Counter
from datetime import datetime
import hashlib
import json
import math
from typing import Any

VERSION = "poisson_v1"
MIN_LEAGUE = 20
MIN_VENUE = 5
TAIL_TOLERANCE = 1e-12


def poisson_distribution(mean: float) -> list[float]:
    if not math.isfinite(mean) or not 0 <= mean <= 20:
        raise ValueError("Média de gols fora do domínio suportado (0 a 20). Revise os dados.")
    probabilities = [math.exp(-mean)]
    for k in range(1, 201):
        if 1 - math.fsum(probabilities) <= TAIL_TOLERANCE:
            return probabilities
        probabilities.append(probabilities[-1] * mean / k)
    raise ValueError("Não foi possível limitar o erro numérico da distribuição.")


def markets(home_mean: float, away_mean: float) -> dict[str, Any]:
    home, away = poisson_distribution(home_mean), poisson_distribution(away_mean)
    cells = [(h, a, ph * pa) for h, ph in enumerate(home) for a, pa in enumerate(away)]
    mass = math.fsum(p for _, _, p in cells)

    def probability(predicate) -> float:
        return math.fsum(p for h, a, p in cells if predicate(h, a)) / mass

    return {
        "probabilidades": {
            "mandante": probability(lambda h, a: h > a),
            "empate": probability(lambda h, a: h == a),
            "visitante": probability(lambda h, a: h < a),
            **{f"over_{limit}": probability(lambda h, a: h + a > limit) for limit in (0.5, 1.5, 2.5, 3.5)},
            "ambas_marcam": probability(lambda h, a: h > 0 and a > 0),
        },
        "placares_mais_provaveis": [dict(mandante=h, visitante=a, probabilidade=p / mass)
                                    for h, a, p in sorted(cells, key=lambda cell: (-cell[2], cell[0], cell[1]))[:5]],
        "precisao_numerica": {"massa_omitida_antes_normalizacao": max(0.0, 1 - mass),
                              "max_gols_mandante": len(home) - 1, "max_gols_visitante": len(away) - 1},
    }


def predict(target: dict[str, Any], matches: list[dict[str, Any]], *, now: datetime) -> dict[str, Any]:
    if now.tzinfo is None:
        raise ValueError("O horário do cálculo deve incluir fuso.")
    kickoff = target.get("data_hora")
    if target.get("status") != "aguardando" or kickoff is None or kickoff <= now:
        raise ValueError("Selecione uma partida futura, com data definida e status aguardando na base local.")
    if target["coletado_em"] > now:
        raise ValueError("A captura da partida é posterior ao horário do cálculo.")
    if target["mandante_id"] == target["visitante_id"]:
        raise ValueError("Mandante e visitante devem ser diferentes.")
    training, excluded = [], []
    seen: set[int] = set()
    scope = (target["origem"], target["campeonato_id"], target["temporada"])
    for match in matches:
        if (match["origem"], match["campeonato_id"], match["temporada"]) != scope:
            raise ValueError("A amostra mistura origens, campeonatos ou temporadas.")
        if match["id"] in seen:
            raise ValueError("Há IDs duplicados na amostra de treinamento.")
        seen.add(match["id"])
        reason = None
        if match["id"] == target["id"]:
            reason = "partida_alvo"
        elif match["status"] != "encerrado":
            reason = "nao_encerrado"
        elif any(type(match[field]) is not int or match[field] < 0
                 for field in ("placar_mandante", "placar_visitante")):
            reason = "placar_incompleto_ou_invalido"
        elif match["data_hora"] is None:
            reason = "sem_data"
        elif match["data_hora"] >= now or match["data_hora"] > match["coletado_em"]:
            reason = "data_incompativel"
        elif match["coletado_em"] > now:
            reason = "captura_posterior_ao_calculo"
        if reason:
            excluded.append({"partida_id": match["id"], "motivo": reason})
        else:
            training.append(match)
    home_rows = [m for m in training if m["mandante_id"] == target["mandante_id"]]
    away_rows = [m for m in training if m["visitante_id"] == target["visitante_id"]]
    if len(training) < MIN_LEAGUE or len(home_rows) < MIN_VENUE or len(away_rows) < MIN_VENUE:
        raise ValueError(f"Amostra insuficiente: liga={len(training)}, mandante em casa={len(home_rows)}, "
                         f"visitante fora={len(away_rows)}. Mínimos: {MIN_LEAGUE}/{MIN_VENUE}/{MIN_VENUE}.")

    def average(rows: list[dict[str, Any]], field: str) -> float:
        return sum(row[field] for row in rows) / len(rows)

    league_home = average(training, "placar_mandante")
    league_away = average(training, "placar_visitante")
    if league_home == 0 or league_away == 0:
        raise ValueError("Média da liga igual a zero; não é possível estimar forças relativas.")
    attack_home = average(home_rows, "placar_mandante") / league_home
    defense_home = average(home_rows, "placar_visitante") / league_away
    attack_away = average(away_rows, "placar_visitante") / league_away
    defense_away = average(away_rows, "placar_mandante") / league_home
    lambda_home = league_home * attack_home * defense_away
    lambda_away = league_away * attack_away * defense_home
    fingerprint = json.dumps(sorted(training, key=lambda m: m["id"]), sort_keys=True, default=str)
    return {
        "modelo": VERSION, "calculado_em": now.isoformat(),
        "partida": {k: target[k] for k in ("id", "origem", "campeonato_id", "temporada", "mandante_id", "visitante_id", "data_hora")},
        "captura_partida_id": str(target["captura_id"]), "agenda_observada_em": target["coletado_em"].isoformat(),
        "amostra": {"liga": len(training), "mandante_em_casa": len(home_rows), "visitante_fora": len(away_rows),
                    "excluidos": len(excluded), "motivos": dict(Counter(e["motivo"] for e in excluded)),
                    "ids_utilizados": sorted(m["id"] for m in training), "detalhes_exclusoes": excluded,
                    "capturas_utilizadas": sorted({str(m["captura_id"]) for m in training}),
                    "ultima_coleta_utilizada": max(m["coletado_em"] for m in training).isoformat(),
                    "sha256_dados": hashlib.sha256(fingerprint.encode()).hexdigest()},
        "parametros": {"min_jogos_liga": MIN_LEAGUE, "min_jogos_por_mando": MIN_VENUE,
                       "media_liga_mandante": league_home, "media_liga_visitante": league_away,
                       "ataque_mandante": attack_home, "defesa_mandante": defense_home,
                       "ataque_visitante": attack_away, "defesa_visitante": defense_away},
        "gols_esperados_modelo": {"mandante": lambda_home, "visitante": lambda_away},
        **markets(lambda_home, lambda_away),
        "confianca": None,
        "limitacoes": ["Modelo inicial sem backtesting ou calibração; não há taxa de acerto comprovada.",
                       "Gols independentes e forças constantes: não considera escalações, lesões ou mudanças recentes.",
                       "Médias por mando sem regularização; amostras pequenas podem gerar estimativas extremas.",
                       "Agenda e resultados vêm de capturas locais e podem estar desatualizados.",
                       "Gols esperados do modelo não são xG de finalizações fornecido por uma fonte.",
                       "Esta saída não é um registro imutável de previsão nem um backtest."],
    }
