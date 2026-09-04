"""Carregamento compartilhado de dados para as páginas Streamlit."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import streamlit as st

from futebol_analytics.api.client import DadosFutebolClient
from futebol_analytics.config.settings import Settings


FUSO_SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def formatar_horario_atualizacao(agora: datetime | None = None) -> str:
    """Retorna um horário legível no fuso de São Paulo."""
    instante = agora or datetime.now(tz=FUSO_SAO_PAULO)
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=FUSO_SAO_PAULO)
    else:
        instante = instante.astimezone(FUSO_SAO_PAULO)
    return instante.strftime("%d/%m/%Y às %H:%M:%S")


@st.cache_data(ttl=60, max_entries=10, show_spinner=False)
def carregar_campeonatos(temporada: str = "2026") -> list[dict[str, Any]]:
    settings = Settings.from_env()
    with DadosFutebolClient(settings) as client:
        return client.listar_campeonatos(temporada=temporada)


@st.cache_data(ttl=60, max_entries=10, show_spinner=False)
def carregar_rodadas(campeonato_id: int) -> list[dict[str, Any]]:
    settings = Settings.from_env()
    with DadosFutebolClient(settings) as client:
        return client.consultar_rodadas(campeonato_id)


@st.cache_data(ttl=60, max_entries=10, show_spinner=False)
def carregar_tabela(campeonato_id: int) -> dict[str, Any]:
    settings = Settings.from_env()
    with DadosFutebolClient(settings) as client:
        return client.consultar_tabela(campeonato_id)
