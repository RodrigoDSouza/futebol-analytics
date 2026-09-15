"""Ponto de entrada da interface web do Futebol Analytics."""

import streamlit as st
from pathlib import Path


PAGES = Path(__file__).resolve().parents[1] / "futebol_painel" / "app_pages"


st.set_page_config(
    page_title="Futebol Analytics",
    page_icon="⚽",
    layout="wide",
)

try:
    # Segredos na raiz do Streamlit passam ao ambiente usado pelos clientes existentes.
    st.secrets.to_dict()
except FileNotFoundError:
    pass  # Desenvolvimento local continua usando .env.

pagina = st.navigation(
    [
        st.Page(
            PAGES / "integrado.py",
            title="Central integrada",
            icon=":material/hub:",
            default=True,
        ),
        st.Page(
            PAGES / "analises.py",
            title="Análises",
            icon=":material/analytics:",
        ),
        st.Page(
            PAGES / "classificacao.py",
            title="Classificação",
            icon=":material/leaderboard:",
        ),
    ],
    position="top",
)

st.title(pagina.title, icon=pagina.icon)
st.caption("Premier League e Brasileirão · agenda, gols e validação de modelos")
pagina.run()
