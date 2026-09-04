"""Página de classificação dos campeonatos."""

import streamlit as st

from futebol_analytics.api.exceptions import DadosFutebolError
from futebol_analytics.config.settings import ConfigurationError
from futebol_analytics.ui.data import (
    carregar_campeonatos,
    carregar_tabela,
    formatar_horario_atualizacao,
)


try:
    with st.spinner("Consultando campeonatos..."):
        campeonatos = carregar_campeonatos()
    campeonato = st.selectbox(
        "Campeonato",
        campeonatos,
        format_func=lambda item: f"{item['nome']} · {item['temporada']}",
        key="classificacao_campeonato",
    )
    with st.spinner("Consultando classificação..."):
        tabela = carregar_tabela(campeonato["id"])
    st.caption(
        f":material/update: Dados atualizados em {formatar_horario_atualizacao()}"
    )
    classificacao = tabela.get("classificacao", [])

    if not classificacao:
        st.warning("A API não retornou uma classificação para este campeonato.")
        st.stop()

    lider = classificacao[0]
    with st.container(horizontal=True):
        st.metric("Líder", lider["time"]["nome"], border=True)
        st.metric("Pontos", lider["pontos"], border=True)
        st.metric(
            "Aproveitamento",
            f"{lider.get('aproveitamento', 0)}%",
            border=True,
        )
        st.metric("Saldo de gols", lider["saldo"], border=True)

    st.subheader("Pontos por time")
    dados_grafico = [
        {"Time": item["time"]["sigla"], "Pontos": item["pontos"]}
        for item in classificacao
    ]
    st.bar_chart(dados_grafico, x="Time", y="Pontos", horizontal=True)

    st.subheader("Tabela completa")
    linhas = [
        {
            "Posição": item["posicao"],
            "Time": item["time"]["nome"],
            "Pontos": item["pontos"],
            "Jogos": item["jogos"],
            "Vitórias": item["vitorias"],
            "Empates": item["empates"],
            "Derrotas": item["derrotas"],
            "Gols pró": item["gols_pro"],
            "Gols contra": item["gols_contra"],
            "Saldo": item["saldo"],
            "Aproveitamento": item.get("aproveitamento"),
        }
        for item in classificacao
    ]
    st.dataframe(
        linhas,
        column_config={
            "Posição": st.column_config.NumberColumn(pinned=True),
            "Time": st.column_config.TextColumn(pinned=True),
            "Aproveitamento": st.column_config.NumberColumn(format="%.1f%%"),
        },
        hide_index=True,
        width="stretch",
    )
except (ConfigurationError, DadosFutebolError) as exc:
    st.error(str(exc))
