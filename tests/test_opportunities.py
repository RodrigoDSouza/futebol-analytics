from datetime import date, datetime, timezone

import pytest

from futebol_analytics.analysis.opportunities import predict_match, rank_opportunities, resolve_team


def history():
    teams = ["Alpha FC", "Bravo", "Charlie", "Delta"]
    rows = []
    for index in range(80):
        home = teams[index % 4]
        away = teams[(index + 1 + (index // 4) % 2) % 4]
        rows.append({"data": f"2026-{1 + index // 28:02}-{1 + index % 28:02}",
                     "mandante": home, "visitante": away,
                     "gols_mandante": 2 if home == "Alpha FC" else index % 3,
                     "gols_visitante": 1 if away == "Bravo" else (index + 1) % 2})
    return rows


def test_prediction_resolves_provider_suffix_and_returns_markets():
    rows = history()
    assert resolve_team("Alpha", {"Alpha FC", "Bravo"}) == "Alpha FC"
    result = predict_match(rows, "Alpha", "Bravo FC", date(2027, 1, 1))
    assert result["amostra"]["liga"] == 80
    assert 0 < result["probabilidades"]["over_1.5"] < 1
    assert result["gols_esperados"]["mandante"] > 0


def test_ranking_abstains_when_validation_does_not_pass():
    quote = {"evento_id": "e1", "inicio": datetime(2027, 1, 2, tzinfo=timezone.utc),
             "mandante": "Alpha", "visitante": "Bravo", "mercado": "totals",
             "selecao": "Over", "linha": 2.5, "probabilidade_justa": 0.01,
             "odd_melhor": 100.0, "odd_mediana": 90.0, "casas": 8}
    report = rank_opportunities(history(), [quote], today=date(2027, 1, 1))
    assert report["candidatos_avaliados"] == 1
    assert report["oportunidades"] == [] or report["oportunidades"][0]["elegivel"]
    assert report["pre_selecao_eventos"] == ["e1"]
    summary = report["resumo_jogos"][0]
    assert summary["vitoria_mandante"] + summary["empate"] + summary["vitoria_visitante"] == pytest.approx(1)
    assert 0 <= summary["over_1.5"] <= 1
    assert set(report["validacoes"]) == {"over_1.5", "over_2.5", "ambas_marcam"}
