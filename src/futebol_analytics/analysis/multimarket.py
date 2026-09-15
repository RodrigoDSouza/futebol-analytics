"""Baseline histórico por mando. Não é probabilidade calibrada nem recomendação."""

from datetime import date
import math


def estimate(rows: list[dict], home: str, away: str, cutoff: date) -> dict:
    eligible = [r for r in rows if date.fromisoformat(str(r['data'])) < cutoff]
    homes = sorted([r for r in eligible if r['mandante'] == home], key=lambda r: str(r['data']), reverse=True)[:10]
    aways = sorted([r for r in eligible if r['visitante'] == away], key=lambda r: str(r['data']), reverse=True)[:10]
    # Confrontos presentes nos dois recortes entram uma única vez na frequência.
    sample = {(str(r['data']), r['mandante'], r['visitante']): r for r in homes + aways}
    specs = []
    for field, lines in [('gols', (1.5, 2.5, 3.5)), ('escanteios', (8.5, 9.5, 10.5, 11.5)),
                         ('amarelos', (3.5, 4.5, 5.5))]:
        for line in lines:
            for side in ('mais', 'menos'):
                specs.append((f'{field}_{side}_{line}', field, side, line))
    specs += [(k, 'gols', k, None) for k in ('mandante', 'empate', 'visitante', 'ambas_sim', 'ambas_nao')]
    markets = []
    for key, field, side, line in specs:
        def valid(r):
            return all(type(r.get(f'{field}_{team}')) is int and r[f'{field}_{team}'] >= 0 for team in ('mandante', 'visitante'))
        usable = [r for r in sample.values() if valid(r)]
        n_home, n_away = sum(valid(r) for r in homes), sum(valid(r) for r in aways)
        item = {'mercado': key, 'n': len(usable), 'n_mandante_casa': n_home, 'n_visitante_fora': n_away,
                'status': 'amostra_insuficiente', 'probabilidade_estimada': None}
        if n_home >= 5 and n_away >= 5:
            def hit(r):
                h, a = r[f'{field}_mandante'], r[f'{field}_visitante']
                if side == 'mais': return h + a > line
                if side == 'menos': return h + a < line
                if side == 'mandante': return h > a
                if side == 'visitante': return h < a
                if side == 'empate': return h == a
                if side == 'ambas_sim': return h > 0 and a > 0
                return h == 0 or a == 0
            wins, n = sum(hit(r) for r in usable), len(usable)
            p = wins / n
            z = 1.96
            centre = (p + z*z/(2*n))/(1+z*z/n)
            radius = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/(1+z*z/n)
            item.update(status='experimental', ocorrencias=wins,
                        probabilidade_estimada=(wins+1)/(n+(3 if side in ('mandante', 'empate', 'visitante') else 2)), frequencia=p,
                        intervalo_frequencia_95=[centre-radius, centre+radius])
        if field == 'amarelos':
            item['regra'] = 'Somente cartões amarelos do CSV; não equivale automaticamente ao total de cartões da casa.'
        markets.append(item)
    return {'modelo': 'frequencia_por_mando_laplace_v1', 'mercados': markets,
            'amostra': [dict(data=k[0], mandante=k[1], visitante=k[2]) for k in sorted(sample)],
            'limitacoes': ['Baseline sem calibração/backtesting; intervalo descreve frequência, não certeza sobre o próximo jogo.',
                          'Últimos dez jogos por mando da temporada; mínimo cinco válidos de cada equipe por mercado.',
                          'Não ajusta força dos adversários, escalação ou árbitro.']}
