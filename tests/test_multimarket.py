from datetime import date, datetime, timezone

import pytest

from futebol_analytics.analysis.multimarket import estimate
from futebol_analytics.daily import plan


def rows():
    return [dict(data=f'2026-09-{i:02}', mandante='Home', visitante='Away', gols_mandante=2,
                 gols_visitante=1, escanteios_mandante=6, escanteios_visitante=4,
                 amarelos_mandante=2, amarelos_visitante=1) for i in range(1, 11)]


def test_markets_complements_and_no_duplicate_sample():
    result = estimate(rows(), 'Home', 'Away', date(2026, 9, 14))
    markets = {m['mercado']: m for m in result['mercados']}
    assert len(result['amostra']) == 10
    assert markets['gols_mais_2.5']['ocorrencias'] == 10
    assert markets['gols_mais_2.5']['probabilidade_estimada'] + markets['gols_menos_2.5']['probabilidade_estimada'] == pytest.approx(1)
    assert markets['amarelos_menos_3.5']['regra']
    assert sum(markets[k]['probabilidade_estimada'] for k in ('mandante', 'empate', 'visitante')) == pytest.approx(1)


def test_missing_not_zero_and_target_date_excluded():
    data = rows()
    for row in data:
        row['escanteios_mandante'] = None
    data.append(dict(data[-1], data='2026-09-14'))
    result = estimate(data, 'Home', 'Away', date(2026, 9, 14))
    assert len(result['amostra']) == 10
    assert all(m['probabilidade_estimada'] is None for m in result['mercados'] if m['mercado'].startswith('escanteios'))


def test_small_sample_abstains():
    assert all(m['status']=='amostra_insuficiente' for m in estimate(rows()[:4], 'Home', 'Away', date(2026, 9, 14))['mercados'])


def fixture(mid=1):
    return dict(id=mid, utcDate='2026-09-14T23:00:00Z', status='TIMED', competition={'code': 'PL'},
                homeTeam={'id': 1, 'name': 'Home'}, awayTeam={'id': 2, 'name': 'Away'})


def history(*args):
    return {'partidas': rows(), 'arquivo': {'id': 'sample'}, 'resumo': {'ultima_data': '2026-09-13'}}


def test_daily_queue_not_recommendations():
    now = datetime(2026, 9, 14, 18, tzinfo=timezone.utc)
    captures = [{'provedor': 'football-data', 'fim_coleta': now.isoformat(), 'partidas': [fixture(i) for i in range(5)]}]
    result = plan(captures, now.date(), now, history, {})
    assert len(result['fila_betano']) == 3
    assert result['indicacoes'] == []


def test_daily_rejects_old_history_and_unknown_status():
    now = datetime(2026, 9, 14, 18, tzinfo=timezone.utc)
    f = fixture()
    f['status'] = 'invalid'
    captures = [{'provedor': 'football-data', 'fim_coleta': now.isoformat(), 'partidas': [f]}]
    assert not plan(captures, now.date(), now, history, {})['fila_betano']
    f['status'] = 'TIMED'
    def stale(*args):
        h = history()
        h['resumo']['ultima_data'] = '2026-09-06'
        return h
    assert not plan(captures, now.date(), now, stale, {})['fila_betano']
