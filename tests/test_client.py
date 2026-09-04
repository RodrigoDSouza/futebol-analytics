import httpx
import pytest

from futebol_analytics.api.client import DadosFutebolClient
from futebol_analytics.api.exceptions import DadosFutebolResponseError
from futebol_analytics.config.settings import Settings


def make_settings() -> Settings:
    return Settings(api_key="chave-de-teste", base_url="https://example.test")


def test_consultar_perfil_envia_autenticacao() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/me"
        assert request.headers["Authorization"] == "Bearer chave-de-teste"
        return httpx.Response(200, json={"data": {"plano": "free"}})

    with DadosFutebolClient(
        make_settings(), transport=httpx.MockTransport(handler)
    ) as client:
        profile = client.consultar_perfil()

    assert profile == {"plano": "free"}


def test_listar_campeonatos_envia_filtros_documentados() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["temporada"] == "2026"
        assert request.url.params["tipo"] == "pontos-corridos"
        return httpx.Response(
            200,
            json={
                "data": [{"id": 3, "nome": "Brasileirão Série A"}],
                "meta": {"total": 1},
            },
        )

    with DadosFutebolClient(
        make_settings(), transport=httpx.MockTransport(handler)
    ) as client:
        championships = client.listar_campeonatos(
            temporada="2026", tipo="pontos-corridos"
        )

    assert championships[0]["id"] == 3


def test_erro_http_preserva_status_sem_expor_chave() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"erro": "Não autorizado", "mensagem": "API Key inválida"},
        )

    with DadosFutebolClient(
        make_settings(), transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(DadosFutebolResponseError) as raised:
            client.consultar_perfil()

    assert raised.value.status_code == 401
    assert str(raised.value) == "API Key inválida"
    assert "chave-de-teste" not in str(raised.value)


def test_consultar_rodadas_usa_id_no_caminho() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/campeonatos/3/rodadas"
        return httpx.Response(
            200,
            json={"data": [{"numero": 1, "partidas": []}]},
        )

    with DadosFutebolClient(
        make_settings(), transport=httpx.MockTransport(handler)
    ) as client:
        rounds = client.consultar_rodadas(3)

    assert rounds == [{"numero": 1, "partidas": []}]


def test_consultar_tabela_exige_objeto_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/campeonatos/3/tabela"
        return httpx.Response(200, json={"data": []})

    with DadosFutebolClient(
        make_settings(), transport=httpx.MockTransport(handler)
    ) as client:
        with pytest.raises(DadosFutebolResponseError, match="tabela"):
            client.consultar_tabela(3)


def test_consultas_rejeitam_id_nao_positivo() -> None:
    with DadosFutebolClient(
        make_settings(), transport=httpx.MockTransport(lambda request: None)
    ) as client:
        with pytest.raises(ValueError, match="inteiro positivo"):
            client.consultar_rodadas(0)
