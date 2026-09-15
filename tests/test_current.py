import httpx
import pytest
from futebol_analytics.api.current import collect

@pytest.fixture(autouse=True)
def keys(monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_API_KEY", "test-secret")
    monkeypatch.setenv("SPORTMONKS_API_TOKEN", "test-secret")

def test_football_data_request():
    def handler(request):
        assert request.headers["X-Auth-Token"] == "test-secret"
        assert request.url.params["date"] == "2026-09-14"
        assert "dateFrom" not in request.url.params
        assert "dateTo" not in request.url.params
        return httpx.Response(200, json={"matches": [{"id": 1}]})
    result = collect("football-data", "2026-09-14", transport=httpx.MockTransport(handler))
    assert result["jogos"] == 1

def test_football_data_uses_explicit_competition_filter():
    def handler(request):
        assert request.url.params['competitions'] == 'CLI'
        return httpx.Response(200, json={'matches': []})
    result = collect('football-data', '2026-09-15', competitions=('CLI',),
                     transport=httpx.MockTransport(handler))
    assert result['competicoes_solicitadas'] == ['CLI']

def test_sportmonks_pagination_and_redaction():
    def handler(request):
        page = int(request.url.params["page"])
        assert request.url.params["include"] == "participants;scores;state;statistics.type"
        return httpx.Response(200, json={"data": [{"id": page}],
            "pagination": {"has_more": page == 1, "next_page": "url?api_token=test-secret"}})
    result = collect("sportmonks", "2026-09-14", transport=httpx.MockTransport(handler))
    assert result["jogos"] == 2
    assert "test-secret" not in str(result)

@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_no_retry_and_safe_error(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="test-secret")
    with pytest.raises(ValueError) as error:
        collect("sportmonks", "2026-09-14", transport=httpx.MockTransport(handler))
    assert len(calls) == 1
    assert "test-secret" not in str(error.value)

@pytest.mark.parametrize("payload", [{"data": []}, {"data": [{"id": 1}, {"id": 1}]}, {"error": "bad"}])
def test_incomplete_rejected(payload):
    with pytest.raises(ValueError):
        collect("sportmonks", "2026-09-14", transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))

def test_missing_key_does_not_connect(monkeypatch):
    monkeypatch.setenv("SPORTMONKS_API_TOKEN", "")
    with pytest.raises(ValueError, match="SPORTMONKS_API_TOKEN"):
        collect("sportmonks", "2026-09-14")
