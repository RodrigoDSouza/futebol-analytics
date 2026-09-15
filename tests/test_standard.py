from datetime import date

from futebol_analytics.standard import collect_standard


def test_standard_covers_sao_paulo_day_from_two_utc_dates():
    calls = []
    def fetch(provider, day, *, competitions):
        calls.append((day, competitions[0]))
        code = competitions[0]
        fixtures = [
            {'id': 1, 'utcDate': '2026-09-15T03:00:00Z', 'competition': {'code': code}},
            {'id': 2, 'utcDate': '2026-09-16T02:30:00Z', 'competition': {'code': code}},
            {'id': 3, 'utcDate': '2026-09-16T03:30:00Z', 'competition': {'code': code}},
        ]
        return {'jogos': len(fixtures), 'partidas': fixtures}

    result = collect_standard(date(2026, 9, 15), fetch=fetch, copa_fetch=lambda day: [])
    assert len(calls) == 8
    assert {day for day, _ in calls} == {'2026-09-15', '2026-09-16'}
    assert all([game['id'] for game in result['competicoes'][name]['jogos']] == [1, 2]
               for name in ('brasileirao', 'premier_league', 'champions_league', 'libertadores'))
    assert result['competicoes']['sul_americana']['status'] == 'sem_fonte_validada'


def test_incomplete_provider_is_reported_without_partial_games():
    def fetch(provider, day, *, competitions):
        if competitions == ('PL',) and day == '2026-09-16':
            raise ValueError('HTTP 403')
        return {'jogos': 1, 'partidas': [{'id': 9, 'utcDate': '2026-09-15T10:00:00Z',
                                        'competition': {'code': competitions[0]}}]}
    result = collect_standard(date(2026, 9, 15), fetch=fetch,
                              copa_fetch=lambda day: (_ for _ in ()).throw(ValueError('sem plano')))
    assert result['competicoes']['premier_league']['status'] == 'erro'
    assert result['competicoes']['premier_league']['jogos'] == []
    assert result['competicoes']['copa_do_brasil']['status'] == 'erro'
