from datetime import datetime, timedelta, timezone

import httpx
import pytest

from futebol_analytics.api.league import collect_premier_season
from futebol_analytics.analysis.tracker import track_focus


def test_premier_capture_rejects_incomplete_response(monkeypatch):
    monkeypatch.setenv('FOOTBALL_DATA_API_KEY', 'test-token')
    def handler(request):
        assert request.url.params['season'] == '2026'
        assert request.url.params['limit'] == '500'
        return httpx.Response(200, json={'resultSet': {'count': 2}, 'matches': [
            {'id': 1, 'competition': {'code': 'PL'}}]})
    with pytest.raises(ValueError, match='incompleta'):
        collect_premier_season(2026, transport=httpx.MockTransport(handler))


def test_tracker_only_exposes_benchmark_when_sources_are_recent():
    now = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)
    finished = [{'id': i, 'utcDate': '2026-09-14T19:00:00Z', 'status': 'FINISHED',
                 'score': {'duration': 'REGULAR', 'fullTime': {'home': 2 if i < 10 else 1, 'away': 1}}}
                for i in range(40)]
    upcoming = {'id': 99, 'utcDate': '2026-09-18T19:00:00Z', 'status': 'SCHEDULED',
                'homeTeam': {'name': 'A'}, 'awayTeam': {'name': 'B'}}
    premier = {'capturado_em': now.isoformat(), 'temporada_inicio': 2026,
               'jogos': finished + [upcoming]}
    brazil = {'ultima_coleta': now.isoformat(), 'temporada': '2026',
              'partidas': [dict(data='2026-09-14', gols_mandante=2 if i < 10 else 1,
                                gols_visitante=1) for i in range(40)]}
    report = track_focus(premier, brazil, [], now)
    assert report['taxas']['premier_league']['taxa_suavizada'] == 11/42
    assert report['taxas_over_1_5']['premier_league']['taxa_suavizada'] == 41/42
    assert report['agenda_7_dias']['premier_league'][0]['taxa_liga_over_1_5'] == 41/42
    assert report['agenda_7_dias']['premier_league'][0]['taxa_liga_over_2_5'] == 11/42
    assert report['taxas_ambos_marcam']['premier_league']['taxa_suavizada'] == 41/42
    assert report['agenda_7_dias']['premier_league'][0]['taxa_liga_ambos_marcam'] == 41/42
    assert report['indicacoes'] == []
    stale = {**premier, 'capturado_em': (now-timedelta(days=2)).isoformat()}
    assert track_focus(stale, brazil, [], now)['agenda_7_dias']['premier_league'][0]['taxa_liga_over_2_5'] is None
    assert track_focus(stale, brazil, [], now)['agenda_7_dias']['premier_league'][0]['taxa_liga_over_1_5'] is None
    assert track_focus(stale, brazil, [], now)['agenda_7_dias']['premier_league'][0]['taxa_liga_ambos_marcam'] is None
