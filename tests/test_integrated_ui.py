from pathlib import Path
import pytest

pytest.importorskip('streamlit')
from streamlit.testing.v1 import AppTest
from futebol_analytics.database.store import DatabaseError


def test_ui_survives_missing_database_without_api_requests(monkeypatch):
    def unavailable(*args, **kwargs):
        raise DatabaseError('indisponivel')
    def forbidden(*args, **kwargs):
        pytest.fail('A abertura do painel nao deve consumir API')
    monkeypatch.setattr('futebol_analytics.database.csv_store.read_csv', unavailable)
    monkeypatch.setattr('futebol_analytics.database.forecast.upcoming', unavailable)
    monkeypatch.setattr('futebol_analytics.api.current.collect', forbidden)
    app = AppTest.from_file(str(Path('src/futebol_painel/web_app.py').resolve())).run(timeout=20)
    assert not app.exception
    assert app.title[0].value == 'Central integrada'
    assert len(app.info) >= 3


def test_focus_view_renders_both_markets_from_existing_report(monkeypatch):
    def unavailable(*args, **kwargs):
        raise DatabaseError('indisponivel')
    monkeypatch.setattr('futebol_analytics.database.csv_store.read_csv', unavailable)
    monkeypatch.setattr('futebol_analytics.database.forecast.upcoming', unavailable)
    rate = {'jogos': 40, 'ocorrencias': 20, 'taxa_suavizada': 0.5}
    quality = {'captura_recente': True, 'resultado_recente': True,
               'ultimo_resultado': '2026-09-14'}
    fixture = {'inicio': '2026-09-18T19:00:00+00:00', 'mandante': 'A', 'visitante': 'B',
               'taxa_liga_over_1_5': 0.5, 'taxa_liga_over_2_5': 0.5,
               'taxa_liga_ambos_marcam': 0.5}
    report = {'calculado_em': '2026-09-15T12:00:00+00:00',
              'taxas': {'premier_league': rate, 'brasileirao': rate},
              'taxas_over_1_5': {'premier_league': rate, 'brasileirao': rate},
              'taxas_ambos_marcam': {'premier_league': rate, 'brasileirao': rate},
              'qualidade_dados': {'premier_league': quality, 'brasileirao': quality},
              'agenda_7_dias': {'premier_league': [fixture], 'brasileirao': []}}
    app = AppTest.from_file(str(Path('src/futebol_painel/web_app.py').resolve()))
    app.session_state['acompanhamento_foco'] = report
    app.run(timeout=20)
    assert not app.exception
    assert len(app.metric) == 6
    assert all(metric.value == '50.0%' for metric in app.metric)
    assert any('Ambos marcam' in metric.label for metric in app.metric)
