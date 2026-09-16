from datetime import datetime, timezone
from decimal import Decimal

import pytest

from futebol_analytics.database.market_store import (save_model_decisions, save_predictions,
    upcoming_odds)


class Result:
    def fetchall(self):
        return [{"evento_id": "e1", "inicio": datetime(2026, 9, 20, tzinfo=timezone.utc),
                 "mandante": "A", "visitante": "B", "checkpoint": "abertura",
                 "mercado": "totals", "selecao": "Over", "linha": Decimal("2.5"),
                 "observado_em": datetime(2026, 9, 16, tzinfo=timezone.utc), "casas": 8,
                 "odd_mediana": Decimal("1.90"), "odd_melhor": Decimal("2.00"),
                 "probabilidade_justa": Decimal("0.51"), "odd_abertura": Decimal("1.85")}]


class Connection:
    def execute(self, statement, params):
        assert "futebol_odds_consensos" in statement
        assert params[0:2] == ("premier_league", "premier_league")
        return Result()


class Context:
    def __enter__(self): return Connection()
    def __exit__(self, *_): return False


class Store:
    def _connection(self): return Context()


def test_upcoming_odds_normalizes_numeric_values():
    rows = upcoming_odds(Store(), "premier_league",
        now=datetime(2026, 9, 16, tzinfo=timezone.utc))
    assert rows[0]["linha"] == 2.5
    assert rows[0]["probabilidade_justa"] == 0.51


@pytest.mark.parametrize("league,days", [("outra", 14), ("brasileirao", 31)])
def test_upcoming_odds_rejects_invalid_scope(league, days):
    with pytest.raises(ValueError):
        upcoming_odds(Store(), league, days=days)


def test_save_predictions_records_future_probabilities_once():
    captured = {}
    class PredictionConnection:
        def execute(self, statement, params):
            captured["statement"] = statement
            captured["payload"] = params[0].obj
    class PredictionContext:
        def __enter__(self): return PredictionConnection()
        def __exit__(self, *_): return False
    class PredictionStore:
        def _connection(self): return PredictionContext()
    now = datetime(2026, 9, 16, tzinfo=timezone.utc)
    report = {"modelo": "poisson_mando_temporal_v2", "resumo_jogos": [{
        "evento_id": "e1", "inicio": datetime(2026, 9, 20, tzinfo=timezone.utc),
        "mandante": "A", "visitante": "B", "vitoria_mandante": .5, "empate": .25,
        "vitoria_visitante": .25, "over_1.5": .7, "over_2.5": .45,
        "ambas_marcam": .52, "amostra_mandante": 10, "amostra_visitante": 9,
        "ultima_partida": "2026-09-10", "incerteza_aproximada": .15,
        "confianca": "baixa", "precos_entrada": {"over_2.5": {
            "odd": 2.05, "observado_em": now, "checkpoint": "abertura"}}}]}
    assert save_predictions(PredictionStore(), "brasileirao", report, calculated_at=now) == 6
    assert len(captured["payload"]) == 6
    assert "ON CONFLICT" in captured["statement"]
    assert captured["payload"][0]["evidencia"]["inicio"].endswith("+00:00")
    over = next(row for row in captured["payload"] if row["mercado"] == "totals"
                and float(row["linha"]) == 2.5)
    assert over["evidencia"]["odd_entrada"] == 2.05


def test_save_predictions_skips_games_without_odds_event():
    class ForbiddenStore:
        def _connection(self):
            pytest.fail("Não deve abrir conexão quando não há evento de odds")
    report = {"modelo": "poisson_mando_temporal_v2", "resumo_jogos": [{
        "evento_id": "agenda-1", "inicio": datetime(2026, 9, 20, tzinfo=timezone.utc),
        "possui_evento_odds": False, "vitoria_mandante": .5}]}
    assert save_predictions(ForbiddenStore(), "brasileirao", report,
        calculated_at=datetime(2026, 9, 16, tzinfo=timezone.utc)) == 0


def test_model_journal_records_only_eligible_strategy_selection():
    captured = {}
    class JournalConnection:
        def execute(self, statement, params):
            captured["payload"] = params[0].obj
    class JournalContext:
        def __enter__(self): return JournalConnection()
        def __exit__(self, *_): return False
    class JournalStore:
        def _connection(self): return JournalContext()
    opportunity = {"evento_id": "e1", "jogo": "A × B", "mercado": "Mais de 2,5 gols",
        "probabilidade_modelo": .60, "odd_referencia": 2.0, "vantagem": .08,
        "valor_esperado": .20}
    report = {"modelo": "poisson_mando_temporal_dc_v3", "oportunidades": [opportunity]}
    assert save_model_decisions(JournalStore(), "brasileirao", report,
        created_at=datetime(2026, 9, 16, tzinfo=timezone.utc)) == 1
    assert captured["payload"][0]["mercado"] == "totals"
    assert captured["payload"][0]["fracao_banca"] <= .01
