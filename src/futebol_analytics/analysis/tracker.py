"""Acompanhamento de gols com benchmark da liga; não seleciona apostas."""

from datetime import date, datetime, timedelta, timezone
import math
from zoneinfo import ZoneInfo


ZONE = ZoneInfo('America/Sao_Paulo')


def league_rate(rows: list[dict], market_key: str = 'gols_mais_2.5') -> dict:
    if market_key not in ('gols_mais_1.5', 'gols_mais_2.5', 'ambas_sim'):
        raise ValueError('Mercado não suportado no acompanhamento.')
    valid = [r for r in rows if type(r.get('gols_mandante')) is int and
             type(r.get('gols_visitante')) is int and r['gols_mandante'] >= 0 and
             r['gols_visitante'] >= 0]
    n = len(valid)
    hits = sum((r['gols_mandante'] > 0 and r['gols_visitante'] > 0)
               if market_key == 'ambas_sim' else
               (r['gols_mandante'] + r['gols_visitante'] >=
                (2 if market_key == 'gols_mais_1.5' else 3)) for r in valid)
    if not n:
        return {'jogos': 0, 'ocorrencias': 0, 'status': 'amostra_insuficiente', 'taxa_suavizada': None,
                'intervalo_frequencia_95': None}
    frequency = hits / n
    z = 1.96
    centre = (frequency + z*z/(2*n))/(1+z*z/n)
    radius = z*math.sqrt(frequency*(1-frequency)/n + z*z/(4*n*n))/(1+z*z/n)
    return {'jogos': n, 'ocorrencias': hits,
            'status': 'benchmark_historico' if n >= 30 else 'amostra_insuficiente',
            'taxa_suavizada': (hits+1)/(n+2) if n >= 30 else None,
            'intervalo_frequencia_95': [centre-radius, centre+radius]}


def premier_season_rows(capture: dict, now: datetime, days: int = 7) -> tuple[list[dict], list[dict]]:
    results, fixtures = [], []
    for game in capture['jogos']:
        kickoff = datetime.fromisoformat(game['utcDate'].replace('Z', '+00:00'))
        if kickoff.tzinfo is None:
            raise ValueError('Premier: horário sem fuso.')
        if game['status'] == 'FINISHED' and kickoff < now:
            score = game.get('score') or {}
            goals = score.get('fullTime') or {}
            if score.get('duration') == 'REGULAR' and all(type(goals.get(side)) is int
                and goals[side] >= 0 for side in ('home', 'away')):
                results.append({'data': kickoff.astimezone(ZONE).date().isoformat(),
                    'gols_mandante': goals['home'], 'gols_visitante': goals['away']})
        elif game['status'] in ('SCHEDULED', 'TIMED') and now < kickoff <= now+timedelta(days=days):
            fixtures.append({'id': game['id'], 'inicio': kickoff.isoformat(),
                'mandante': game['homeTeam']['name'], 'visitante': game['awayTeam']['name'],
                'status': game['status']})
    return results, sorted(fixtures, key=lambda g: (g['inicio'], g['id']))


def track_focus(premier: dict, brazil: dict, brazil_schedule: list[dict], now: datetime) -> dict:
    if now.tzinfo is None:
        raise ValueError('Horário de avaliação precisa de fuso.')
    pl_results, pl_schedule = premier_season_rows(premier, now)
    rates = {'premier_league': league_rate(pl_results),
             'brasileirao': league_rate(brazil['partidas'])}
    over_1_5_rates = {'premier_league': league_rate(pl_results, 'gols_mais_1.5'),
                      'brasileirao': league_rate(brazil['partidas'], 'gols_mais_1.5')}
    btts_rates = {'premier_league': league_rate(pl_results, 'ambas_sim'),
                  'brasileirao': league_rate(brazil['partidas'], 'ambas_sim')}
    observed = {'premier_league': datetime.fromisoformat(premier['capturado_em']),
                'brasileirao': datetime.fromisoformat(brazil['ultima_coleta'])}
    results = {'premier_league': pl_results, 'brasileirao': brazil['partidas']}
    quality = {}
    for league in rates:
        last_day = max((date.fromisoformat(str(r['data'])) for r in results[league]), default=None)
        age = now - observed[league]
        recent_capture = observed[league].tzinfo is not None and timedelta(0) <= age <= timedelta(hours=24)
        recent_result = last_day is not None and 0 <= (now.astimezone(ZONE).date()-last_day).days <= 3
        quality[league] = {'captura_recente': recent_capture, 'ultimo_resultado': str(last_day) if last_day else None,
                           'resultado_recente': recent_result}
    games = {'premier_league': pl_schedule,
             'brasileirao': [{'id': g['id'], 'inicio': g['data_hora'],
                              'mandante': g['mandante'], 'visitante': g['visitante'],
                              'status': g['status'], 'agenda_observada_em': g['agenda_observada_em']}
                             for g in brazil_schedule]}
    for league, fixtures in games.items():
        for fixture in fixtures:
            fixture['taxa_liga_over_1_5'] = (over_1_5_rates[league]['taxa_suavizada']
                if quality[league]['captura_recente'] and quality[league]['resultado_recente'] else None)
            fixture['taxa_liga_over_2_5'] = (rates[league]['taxa_suavizada']
                if quality[league]['captura_recente'] and quality[league]['resultado_recente'] else None)
            fixture['taxa_liga_ambos_marcam'] = (btts_rates[league]['taxa_suavizada']
                if quality[league]['captura_recente'] and quality[league]['resultado_recente'] else None)
            fixture['indicacao'] = None
    return {'calculado_em': now.astimezone(timezone.utc).isoformat(),
            'mercados': ['gols_mais_1.5', 'gols_mais_2.5', 'ambas_sim'],
            'modelo': 'frequencia_liga_laplace_v1', 'fontes': {
                'premier_league': {'capturado_em': premier['capturado_em'],
                                   'temporada_inicio': premier['temporada_inicio']},
                'brasileirao': {'ultima_coleta': brazil['ultima_coleta'],
                                'temporada': brazil['temporada']}},
            'taxas': rates, 'taxas_over_1_5': over_1_5_rates,
            'taxas_ambos_marcam': btts_rates,
            'qualidade_dados': quality, 'agenda_7_dias': games, 'indicacoes': [],
            'limitacoes': ['A taxa da liga é benchmark igual para todos os jogos; não considera as equipes.',
                           'Wilson descreve a frequência histórica, não a certeza do próximo jogo.',
                           'Sem odds do mesmo mercado e validação contra preços de mercado, não indica apostas.',
                           'Agenda futura e placares podem mudar após esta captura.']}
