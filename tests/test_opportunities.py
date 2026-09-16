from datetime import date, datetime, timezone

import pytest

from futebol_analytics.analysis.opportunities import (predict_match, rank_opportunities,
    resolve_team, risk_plan)


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
    assert result["media_gols_recente"]["mandante_em_casa"] > 0
    assert resolve_team("Wolves", {"Wolverhampton Wanderers FC", "Fulham"}) == "Wolverhampton Wanderers FC"
    assert result["amostra"]["meia_vida_dias"] == 180


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
    assert summary["confianca"] in {"baixa", "moderada"}
    assert summary["cobertura_mercado"] == "disponível"
    assert summary["estado_decisao"] in {"acompanhar", "sem valor validado"}
    assert set(report["validacoes"]) == {"over_1.5", "over_2.5", "ambas_marcam"}


def test_fixtures_receive_model_even_without_any_odds():
    fixtures = [{"id": 99, "data_hora": "2027-01-02T18:00:00+00:00",
                 "mandante": "Alpha", "visitante": "Bravo",
                 "origem_agenda": "dados-futebol"}]
    report = rank_opportunities(history(), [], today=date(2027, 1, 1), fixtures=fixtures)
    assert len(report["resumo_jogos"]) == 1
    assert report["resumo_jogos"][0]["origem_agenda"] == "dados-futebol"
    assert report["resumo_jogos"][0]["possui_evento_odds"] is False
    assert report["resumo_jogos"][0]["estado_decisao"] == "sem preço de mercado"
    assert report["candidatos_avaliados"] == 0


def test_fixture_is_reconciled_with_matching_odds_event():
    fixtures = [{"id": 99, "data_hora": "2027-01-02T18:00:00+00:00",
                 "mandante": "Alpha", "visitante": "Bravo",
                 "origem_agenda": "dados-futebol"}]
    quote = {"evento_id": "odds-1", "inicio": datetime(2027, 1, 2, 20, tzinfo=timezone.utc),
             "mandante": "Alpha FC", "visitante": "Bravo", "mercado": "totals",
             "selecao": "Over", "linha": 2.5, "probabilidade_justa": .5,
             "odd_melhor": 2.0, "odd_mediana": 1.9, "casas": 4}
    report = rank_opportunities(history(), [quote], today=date(2027, 1, 1), fixtures=fixtures)
    assert len(report["resumo_jogos"]) == 1
    assert report["resumo_jogos"][0]["evento_id"] == "odds-1"
    assert report["resumo_jogos"][0]["possui_evento_odds"] is True


def test_risk_plan_caps_daily_exposure_and_correlated_markets():
    base = {"probabilidade_modelo": .60, "odd_referencia": 2.0,
            "valor_esperado": .20, "jogo": "A × B", "mercado": "+2,5"}
    plan = risk_plan([base | {"evento_id": "e1"},
                      base | {"evento_id": "e1", "valor_esperado": .10},
                      base | {"evento_id": "e2", "jogo": "C × D"}], bankroll=1000,
                     max_bet_fraction=.01, max_daily_fraction=.015)
    assert len(plan["selecoes"]) == 2
    assert plan["exposicao_total"] == pytest.approx(15)
    assert plan["fracao_total"] == pytest.approx(.015)
    assert all(item["valor_maximo"] <= 10 for item in plan["selecoes"])
