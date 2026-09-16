"""Métricas de calibração para previsões registradas antes das partidas."""

from __future__ import annotations

from collections import defaultdict
import math
from typing import Any


def calibration_report(rows: list[dict[str, Any]], *, bin_width: float = .1) -> dict[str, Any]:
    if not 0 < bin_width <= .5:
        raise ValueError("Largura de faixa inválida.")
    valid = [row for row in rows
             if type(row.get("probabilidade")) in (int, float)
             and 0 < row["probabilidade"] < 1 and row.get("resultado") in (0, 1, False, True)]
    if not valid:
        return {"avaliadas": 0, "brier": None, "log_loss": None,
                "erro_calibracao": None, "faixas": []}
    bins: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in valid:
        bins[min(int(row["probabilidade"] / bin_width), int(1 / bin_width) - 1)].append(row)
    groups, weighted_error = [], 0.0
    for index, items in sorted(bins.items()):
        predicted = sum(item["probabilidade"] for item in items) / len(items)
        observed = sum(int(item["resultado"]) for item in items) / len(items)
        error = abs(predicted - observed)
        weighted_error += len(items) * error
        groups.append({"faixa": f"{index * bin_width:.0%}–{(index + 1) * bin_width:.0%}",
                       "previsoes": len(items), "probabilidade_media": predicted,
                       "frequencia_observada": observed, "erro_absoluto": error})
    count = len(valid)
    brier = sum((row["probabilidade"] - int(row["resultado"])) ** 2 for row in valid) / count
    log_loss = -sum(int(row["resultado"]) * math.log(max(row["probabilidade"], 1e-12))
                    + (1 - int(row["resultado"])) * math.log(max(1 - row["probabilidade"], 1e-12))
                    for row in valid) / count
    return {"avaliadas": count, "brier": brier, "log_loss": log_loss,
            "erro_calibracao": weighted_error / count, "faixas": groups}


def grouped_calibration(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row.get("mercado"), row.get("selecao"), float(row.get("linha") or 0))].append(row)
    result = []
    for (market, selection, line), items in sorted(groups.items(), key=lambda item: str(item[0])):
        report = calibration_report(items)
        result.append({"mercado": market, "selecao": selection, "linha": line,
                       **{key: report[key] for key in
                          ("avaliadas", "brier", "log_loss", "erro_calibracao")}})
    return result


def closing_value_report(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compara a odd observada na previsão com o consenso de fechamento."""
    valid = []
    for row in rows:
        try:
            entry, closing = float(row.get("odd_entrada")), float(row.get("odd_fechamento"))
        except (TypeError, ValueError):
            continue
        if entry <= 1 or closing <= 1:
            continue
        value = entry / closing - 1
        valid.append({**row, "odd_entrada": entry, "odd_fechamento": closing,
                      "clv": value, "superou_fechamento": value > 0})
    if not valid:
        return {"comparacoes": 0, "clv_medio": None,
                "percentual_superou_fechamento": None, "registros": []}
    return {"comparacoes": len(valid),
            "clv_medio": sum(row["clv"] for row in valid) / len(valid),
            "percentual_superou_fechamento": sum(row["superou_fechamento"] for row in valid) / len(valid),
            "registros": valid}
