"""Ponto de entrada da interface web do Futebol Analytics."""

import streamlit as st


st.set_page_config(
    page_title="Futebol Analytics",
    page_icon="⚽",
    layout="wide",
)

pagina = st.navigation(
    [
        st.Page("app_pages/integrado.py", title="Central integrada", icon=":material/hub:", default=True),
        st.Page(
            "app_pages/analises.py",
            title="Análises",
            icon=":material/analytics:",
        ),
        st.Page(
            "app_pages/classificacao.py",
            title="Classificação",
            icon=":material/leaderboard:",
        ),
    ],
    position="top",
)

st.title(pagina.title, icon=pagina.icon)
st.caption("Premier League e Brasileirão · agenda, gols e validação de modelos")
pagina.run()
