"""Avaliação conjunta inicial de over 2,5 para Premier e Brasileirão."""

from futebol_analytics.analysis.backtest import backtest


def evaluate_focus(premier: dict, brasileirao: dict) -> dict:
    results = {}
    for name, source in [('premier_league', premier), ('brasileirao', brasileirao)]:
        evaluations = {market: backtest(source['partidas'], market)
                       for market in ('gols_mais_1.5', 'gols_mais_2.5', 'ambas_sim')}
        results[name] = {'cobertura': {k: v for k, v in source.items() if k != 'partidas'},
                         'avaliacao': evaluations['gols_mais_2.5'],
                         'avaliacoes': evaluations,
                         'estado_modelo': 'exploratorio; não aprovado para indicações'}
    return {'mercados': ['gols_mais_1.5', 'gols_mais_2.5', 'ambas_sim'], 'ligas': results, 'indicacoes': [],
            'criterio': 'Nenhuma indicação antes de validação futura, odds pré-jogo alinhadas e modelo que supere baseline simples.',
            'limitacoes': ['Backtest retrospectivo sobre versões atuais das fontes; não reproduz capturas disponíveis em cada data.',
                           'Comparação Brier usa apenas partidas que receberam previsão; zero jogos avaliados não é validação.',
                           'Sem odds pré-jogo alinhadas, não estima lucro ou vantagem realizável.']}
