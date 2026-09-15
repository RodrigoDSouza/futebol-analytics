from unittest.mock import Mock

import httpx
import pytest

from futebol_analytics.api.client import DadosFutebolClient
from futebol_analytics.api.exceptions import APIHTTPError, APIResponseError
from futebol_analytics.config.settings import Settings
from futebol_analytics.sync import synchronize


def response_page(number, *, total=2, last=2, item_id=None):
    return {"data": [{"id": item_id or number}],
            "meta": {"total": total, "pagina_atual": number, "ultima_pagina": last}}


def test_complete_collection_before_single_save():
    store = Mock()
    requests = []
    def handler(request):
        assert not store.save.called
        requests.append(request)
        return httpx.Response(200, json=response_page(int(request.url.params["pagina"])))
    with DadosFutebolClient(Settings("fixture-only"), transport=httpx.MockTransport(handler)) as client:
        synchronize(client, store, "partidas", "77", "https://api.dadosfutebol.com.br")
    assert len(requests) == 2
    store.save.assert_called_once()
    args = store.save.call_args.args
    assert len(args[3]["paginas"]) == 2
    assert args[4].tzinfo is not None and args[5] >= args[4]


@pytest.mark.parametrize("failure", ["http", "duplicate", "changing", "missing"])
def test_failed_collection_does_not_save(failure):
    store = Mock()
    def handler(request):
        number = int(request.url.params["pagina"])
        if number == 2 and failure == "http":
            return httpx.Response(429)
        page = response_page(number)
        if number == 2:
            if failure == "duplicate":
                page["data"][0]["id"] = 1
            elif failure == "changing":
                page["meta"]["total"] = 3
            elif failure == "missing":
                page["data"] = []
        return httpx.Response(200, json=page)
    with DadosFutebolClient(Settings("fixture-only"), transport=httpx.MockTransport(handler)) as client:
        with pytest.raises((APIHTTPError, APIResponseError)):
            synchronize(client, store, "partidas", "77", "https://api.dadosfutebol.com.br")
    store.save.assert_not_called()


def test_page_budget_stops_before_next_request():
    client, store = Mock(), Mock()
    client.listar_campeonatos.return_value = response_page(1)
    with pytest.raises(APIResponseError):
        synchronize(client, store, "campeonatos", "2026", "source", max_pages=1)
    assert client.listar_campeonatos.call_count == 1
    store.save.assert_not_called()


@pytest.mark.parametrize("resource,payload", [
    ("tabela", {"data": {"campeonato_id": 77, "classificacao": []}}),
    ("estatisticas", {"data": {"partida_id": 77, "estatisticas": {"mandante": {"gols_esperados": None}}}}),
])
def test_unpaginated_resource_preserved(resource, payload):
    client, store = Mock(), Mock()
    client.consultar_tabela.return_value = payload
    client.consultar_estatisticas.return_value = payload
    synchronize(client, store, resource, "77", "source")
    assert store.save.call_args.args[3] == payload


def test_wrong_championship_never_saved():
    client, store = Mock(), Mock()
    client.consultar_tabela.return_value = {"data": {"campeonato_id": 88, "classificacao": []}}
    with pytest.raises(APIResponseError):
        synchronize(client, store, "tabela", "77", "source")
    store.save.assert_not_called()


def test_complete_unpaginated_collection_is_saved_once():
    store = Mock()
    payload = {"data": [{"id": 91}], "meta": {"total": 1}}
    with DadosFutebolClient(Settings("fixture-only"), transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload))) as client:
        synchronize(client, store, "campeonatos", "2026", "source")
    store.save.assert_called_once()
    assert store.save.call_args.args[3] == {"paginas": [payload]}


@pytest.mark.parametrize("resource,data", [
    ("rodadas", [{"id": 1, "partidas": [{"id": 55, "placar_mandante": None}]}]),
    ("artilharia", [{"id": 7, "gols": 4}]), ("artilharia", []), ("rodadas", []),
])
def test_free_resources_preserve_response(resource, data):
    store = Mock()
    payload = {"data": data, "meta": {"campeonato_id": 3, "total": len(data)}}
    def handler(request):
        assert request.url.path == f"/v1/campeonatos/3/{resource}"
        assert not request.url.query
        return httpx.Response(200, json=payload)
    with DadosFutebolClient(Settings("fixture-only"), transport=httpx.MockTransport(handler)) as client:
        synchronize(client, store, resource, "3", "source")
    store.save.assert_called_once()
    assert store.save.call_args.args[3] == payload


@pytest.mark.parametrize("payload", [
    {"data": [], "meta": {"total": 1}},
    {"data": [], "meta": {"total": 0, "campeonato_id": 4}},
    {"data": [{"id": 1}], "meta": {"total": 1}},
])
def test_incomplete_rounds_never_saved(payload):
    client, store = Mock(), Mock()
    client.consultar_rodadas.return_value = payload
    with pytest.raises(APIResponseError):
        synchronize(client, store, "rodadas", "3", "source")
    store.save.assert_not_called()
