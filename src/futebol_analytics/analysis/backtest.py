"""Avaliação cronológica retrospectiva do baseline, com snapshots atuais."""

from datetime import date
from futebol_analytics.analysis.multimarket import estimate


MARKETS = {'gols_mais_1.5', 'gols_mais_2.5', 'ambas_sim'}


def backtest(rows: list[dict], market_key: str = 'gols_mais_2.5') -> dict:
    if market_key not in MARKETS:
        raise ValueError('Mercado não suportado no backtest.')
    predictions = []
    ordered = sorted(rows, key=lambda r: (str(r['data']), r['mandante'], r['visitante']))
    keys = [(str(r['data']), r['mandante'], r['visitante']) for r in ordered]
    if len(set(keys)) != len(keys):
        raise ValueError('Histórico contém partidas duplicadas.')
    for target in ordered:
        if not all(type(target.get(k)) is int and target[k] >= 0 for k in ('gols_mandante','gols_visitante')):
            continue
        cutoff = date.fromisoformat(str(target['data']))
        history = [r for r in ordered if date.fromisoformat(str(r['data'])) < cutoff]
        result = estimate(history, target['mandante'], target['visitante'], cutoff)
        market = next(m for m in result['mercados'] if m['mercado'] == market_key)
        if market['probabilidade_estimada'] is None:
            continue
        valid = [r for r in history if all(type(r.get(k)) is int and r[k] >= 0 for k in ('gols_mandante','gols_visitante'))]
        def occurred(r):
            if market_key == 'ambas_sim':
                return r['gols_mandante'] > 0 and r['gols_visitante'] > 0
            return r['gols_mandante'] + r['gols_visitante'] >= (2 if market_key == 'gols_mais_1.5' else 3)
        baseline = (1 + sum(occurred(r) for r in valid))/(len(valid)+2)
        observed = int(occurred(target))
        predictions.append({'data':str(target['data']), 'mandante':target['mandante'], 'visitante':target['visitante'],
                            'probabilidade':market['probabilidade_estimada'], 'resultado':observed,
                            'baseline_liga':baseline, 'ultima_data_treino':max(str(r['data']) for r in history)})
    n = len(predictions)
    bins = []
    for start in range(0, 10, 2):
        group = [r for r in predictions if start / 10 <= r['probabilidade'] < (start + 2) / 10 or
                 (start == 8 and r['probabilidade'] == 1)]
        if group:
            bins.append({'faixa': f'{start * 10}-{(start + 2) * 10}%', 'jogos': len(group),
                         'probabilidade_media': sum(r['probabilidade'] for r in group) / len(group),
                         'frequencia_observada': sum(r['resultado'] for r in group) / len(group)})
    brier_model = sum((r['probabilidade']-r['resultado'])**2 for r in predictions)/n if n else None
    brier_league = sum((r['baseline_liga']-r['resultado'])**2 for r in predictions)/n if n else None
    return {'mercado':market_key, 'jogos_avaliados':n, 'jogos_nao_avaliados':len(rows)-n,
            'brier_modelo':brier_model, 'brier_baseline_liga':brier_league,
            'supera_baseline_liga':brier_model < brier_league if n else None,
            'calibracao_por_faixa': bins,
            'previsoes':predictions,
            'limitacoes':['Avaliação retrospectiva com dados da versão atual, não capturas disponíveis em cada data histórica.',
                          'Sem odds históricas alinhadas deste mercado, não mede lucro nem ROI.',
                          'Brier menor é melhor; desempenho nesta amostra não garante desempenho futuro.']}
