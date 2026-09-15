"""Compara previsões retrospectivas com cotações históricas da Premier."""

import csv
from datetime import datetime
import io


def compare_historical_odds(content: str, predictions: list[dict]) -> dict:
    rows = csv.DictReader(io.StringIO(content.lstrip('\ufeff')))
    required = {'Date', 'HomeTeam', 'AwayTeam', 'B365>2.5', 'B365<2.5',
                'B365C>2.5', 'B365C<2.5'}
    if not rows.fieldnames or not required.issubset(rows.fieldnames):
        raise ValueError('CSV sem as cotações históricas necessárias.')
    odds = {}
    for row in rows:
        key = (datetime.strptime(row['Date'], '%d/%m/%Y').date().isoformat(),
               row['HomeTeam'].strip(), row['AwayTeam'].strip())
        if key in odds:
            raise ValueError('CSV contém partidas duplicadas.')
        odds[key] = row
    compared = []
    for prediction in predictions:
        key = (prediction['data'], prediction['mandante'], prediction['visitante'])
        row = odds.get(key)
        if row is None:
            continue
        try:
            opening_over, opening_under, closing_over, closing_under = (
                float(row[field]) for field in ('B365>2.5', 'B365<2.5',
                                         'B365C>2.5', 'B365C<2.5'))
        except (ValueError, TypeError):
            continue
        if min(opening_over, opening_under, closing_over, closing_under) <= 1:
            continue
        opening = (1/opening_over)/(1/opening_over + 1/opening_under)
        closing = (1/closing_over)/(1/closing_over + 1/closing_under)
        compared.append({'resultado': prediction['resultado'],
                         'modelo': prediction['probabilidade'],
                         'baseline_liga': prediction['baseline_liga'],
                         'mercado_abertura': opening, 'mercado_fechamento': closing})
    n = len(compared)
    def brier(field: str) -> float | None:
        return sum((r[field]-r['resultado'])**2 for r in compared)/n if n else None
    return {'jogos_avaliados': n, 'previsoes_sem_odds_alinhadas': len(predictions)-n,
            'brier': {field: brier(field) for field in
                      ('modelo', 'baseline_liga', 'mercado_abertura', 'mercado_fechamento')},
            'fonte': 'Football-Data E0 2025/26; B365 over/under 2,5',
            'indicacoes': [],
            'limitacoes': ['Cotações históricas não são preços disponíveis hoje.',
                          'Probabilidades do mercado removem margem proporcionalmente.',
                          'Backtest usa a versão atual dos dados, não snapshots históricos.',
                          'Uma temporada não valida vantagem futura; sem odds atuais alinhadas.']}
