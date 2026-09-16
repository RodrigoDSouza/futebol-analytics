from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
import pytest

from futebol_analytics.api.the_odds import collect_odds
from futebol_analytics.database.market_store import _consensus_rows, _details, checkpoint


def test_collect_odds_uses_supported_markets_and_redacts_key(monkeypatch):
    monkeypatch.setenv("THE_ODDS_API_KEY", "secret-key")

    def handler(request):
        assert request.url.params["apiKey"] == "secret-key"
        assert request.url.params["markets"] == "h2h,totals"
        assert request.url.params["regions"] == "eu"
        return httpx.Response(200, headers={"x-requests-remaining": "497"}, json=[{
            "id": "event-1", "commence_time": "2026-09-20T15:00:00Z",
            "home_team": "A", "away_team": "B", "bookmakers": []}])

    result = collect_odds("premier_league", transport=httpx.MockTransport(handler))
    assert result["creditos_restantes"] == 497
    assert result["eventos"][0]["id"] == "event-1"
    assert "secret-key" not in str(result)


@pytest.mark.parametrize("status", [401, 422, 429, 500])
def test_collect_odds_has_safe_errors(monkeypatch, status):
    monkeypatch.setenv("THE_ODDS_API_KEY", "secret-key")
    transport = httpx.MockTransport(lambda request: httpx.Response(status, text="secret-key"))
    with pytest.raises(ValueError) as error:
        collect_odds("brasileirao", transport=transport)
    assert "secret-key" not in str(error.value)


def test_checkpoint_retention_windows():
    captured = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    assert checkpoint(captured + timedelta(days=4), captured) == "abertura"
    assert checkpoint(captured + timedelta(hours=24), captured) == "24h"
    assert checkpoint(captured + timedelta(hours=7), captured) == "fechamento"
    assert checkpoint(captured, captured) is None


def test_normalizes_supported_market_rows():
    event = {"id": "e1", "bookmakers": [{"key": "book", "markets": [
        {"key": "h2h", "outcomes": [{"name": "A", "price": 2.1}]},
        {"key": "totals", "outcomes": [{"name": "Over", "price": 1.9, "point": 2.5}]},
        {"key": "unsupported", "outcomes": [{"name": "X", "price": 3.0}]},
    ]}]}
    rows = _details(event, "the-odds-api", "premier_league", datetime.now(timezone.utc))
    assert len(rows) == 2
    assert rows[0]["linha"] == Decimal(0)
    assert rows[1]["linha"] == Decimal("2.5")


def test_consensus_removes_bookmaker_margin():
    now = datetime.now(timezone.utc)
    event = {"id": "e1", "bookmakers": [{"key": "book", "markets": [{"key": "h2h",
        "outcomes": [{"name": "A", "price": 2.0}, {"name": "Draw", "price": 3.2},
                     {"name": "B", "price": 3.8}]}]}]}
    details = _details(event, "the-odds-api", "premier_league", now)
    consensus = _consensus_rows("the-odds-api", "premier_league", "e1",
                                "abertura", now, details)
    assert sum(row["probabilidade_justa"] for row in consensus) == pytest.approx(1)
