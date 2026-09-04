"""Carregamento compartilhado de dados para as páginas Streamlit."""

from typing import Any

import streamlit as st

from futebol_analytics.api.client import DadosFutebolClient
from futebol_analytics.config.settings import Settings


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

