import httpx
import pytest

from futebol_analytics.api.client import DadosFutebolClient
from futebol_analytics.api.exceptions import APIConnectionError, APIHTTPError, APIResponseError, DadosFutebolError
from futebol_analytics.config.settings import Settings
from futebol_analytics.main import main


def client_for(handler):
    return DadosFutebolClient(Settings("fixture-only"), transport=httpx.MockTransport(handler))


def page(data, current=1, last=1):
    return {"data": data, "meta": {"pagina_atual": current, "ultima_pagina": last}}


def test_authentication_and_close():
    observed = []
    def handler(request):
        observed.append(request)
        assert request.headers.get("Authorization", "").startswith("Bearer ")
        assert request.headers["Accept"] == "application/json"
        assert request.url.path == "/v1/me"
        assert request.extensions["timeout"]["read"] == 20
        return httpx.Response(200, json={"data": {"plano": "free"}})
    with client_for(handler) as client:
        assert client.validar_api_key() is None
    assert client._http.is_closed
    assert len(observed) == 1


def test_find_across_pages_without_fixed_id():
    seen = []
    def handler(request):
        current = int(request.url.params["pagina"])
        seen.append(current)
        assert request.url.params["temporada"] == "2026"
        items = [{"id": 77, "nome": "Brasileirão Série B", "temporada": "2026"}] if current == 1 else [
            {"id": 984, "nome": "Brasileirão Série A", "temporada": "2026"}]
        return httpx.Response(200, json=page(items, current, 2))
    with client_for(handler) as client:
        assert client.localizar_brasileirao()["id"] == 984
    assert seen == [1, 2]


@pytest.mark.parametrize("items", [[], [
    {"id": 1, "nome": "Brasileirão Série A", "temporada": "2026"},
    {"id": 2, "nome": "Brasileirão Série A", "temporada": "2026"},
]])
def test_missing_or_ambiguous_championship(items):
    with client_for(lambda request: httpx.Response(200, json=page(items))) as client:
        with pytest.raises(DadosFutebolError, match="única"):
            client.localizar_brasileirao()


@pytest.mark.parametrize("status", [301, 401, 403, 404, 422, 429, 500])
def test_http_errors_are_safe_and_not_retried(status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="response-body-must-not-be-shown", headers={"Location": "https://example.com"})
    with client_for(handler) as client:
        with pytest.raises(APIHTTPError) as exc:
            client.validar_api_key()
        assert exc.value.status_code == status
        assert "response-body" not in str(exc.value)
    assert len(calls) == 1
    assert client._http.is_closed


@pytest.mark.parametrize("error_type", [httpx.ReadTimeout, httpx.ConnectError])
def test_network_failure(error_type):
    def handler(request):
        raise error_type("internal-details", request=request)
    with client_for(handler) as client:
        with pytest.raises(APIConnectionError) as exc:
            client.validar_api_key()
        assert "internal-details" not in str(exc.value)


@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"data": null}', b'{}'])
def test_invalid_json_or_envelope(body):
    with client_for(lambda request: httpx.Response(200, content=body)) as client:
        with pytest.raises(APIResponseError):
            client.validar_api_key()


def test_inconsistent_pagination():
    with client_for(lambda request: httpx.Response(200, json=page([], 1, 2))) as client:
        with pytest.raises(APIResponseError):
            client.listar_campeonatos(pagina=2)


def test_match_filters_and_limit_headers():
    def handler(request):
        assert request.url.path == "/v1/campeonatos/84/partidas"
        assert dict(request.url.params) == {"rodada": "2", "status": "encerrado", "time_id": "9",
            "data_inicio": "2026-01-01", "data_fim": "2026-12-31", "pagina": "2", "por_pagina": "10"}
        return httpx.Response(200, json=page([], 2, 2), headers={"X-RateLimit-Remaining": "45"})
    with client_for(handler) as client:
        client.listar_partidas(84, rodada=2, status="encerrado", time_id=9, data_inicio="2026-01-01",
                              data_fim="2026-12-31", pagina=2, por_pagina=10)
        assert client.rate_limit["X-RateLimit-Remaining"] == "45"


def test_table_and_statistics_preserve_data():
    paths = []
    def handler(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"data": {"estatisticas": {"mandante": {"gols_esperados": None}}}})
    with client_for(handler) as client:
        client.consultar_tabela(84)
        result = client.consultar_estatisticas(92)
        assert result["data"]["estatisticas"]["mandante"]["gols_esperados"] is None
    assert paths == ["/v1/campeonatos/84/tabela", "/v1/partidas/92/estatisticas"]


def test_invalid_page_size_never_calls_api():
    def handler(request):
        pytest.fail("Não deveria fazer requisição")
    with client_for(handler) as client:
        with pytest.raises(ValueError):
            client.listar_campeonatos(por_pagina=101)


def test_cli_missing_key(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DADOS_FUTEBOL_API_KEY", raising=False)
    assert main(["validar-chave"]) == 1
    assert "API Key" in capsys.readouterr().err


def test_complete_unpaginated_championship_list():
    payload = {"data": [{"id": 91, "nome": "Brasileirão Série A", "temporada": "2026"}],
               "meta": {"total": 1}}
    with client_for(lambda request: httpx.Response(200, json=payload)) as client:
        assert client.listar_campeonatos() == payload
        assert client.localizar_brasileirao()["id"] == 91


@pytest.mark.parametrize("meta,pagina", [({"total": 2}, 1), ({"total": 0}, 2),
    ({"total": "0"}, 1), ({"total": 0, "pagina_atual": 1}, 1)])
def test_reject_incomplete_unpaginated_list(meta, pagina):
    with client_for(lambda request: httpx.Response(200, json={"data": [], "meta": meta})) as client:
        with pytest.raises(APIResponseError):
            client.listar_campeonatos(pagina=pagina)
