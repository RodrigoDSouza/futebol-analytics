"""Conferência descritiva de uma cotação atual, sem afirmar vantagem."""

import math


def check_quote(odd: float, league_rate: float | None) -> dict:
    if type(odd) not in (int, float) or not math.isfinite(odd) or odd <= 1:
        raise ValueError('Odd decimal inválida.')
    if league_rate is not None and (type(league_rate) not in (int, float)
                                    or not 0 <= league_rate <= 1):
        raise ValueError('Taxa histórica inválida.')
    return {'odd_decimal': float(odd), 'probabilidade_equilibrio': 1/odd,
            'taxa_historica_liga': league_rate,
            'diferenca_descritiva_pontos_percentuais':
                100*(league_rate-1/odd) if league_rate is not None else None,
            'vantagem_comprovada': False, 'indicacao': None,
            'motivo': 'Taxa da liga não é uma probabilidade calibrada para este jogo; modelo atual não superou essa referência.'}
