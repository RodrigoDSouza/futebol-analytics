from datetime import datetime, timezone
from decimal import Decimal

import pytest

from futebol_analytics.database.market_store import upcoming_odds


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
