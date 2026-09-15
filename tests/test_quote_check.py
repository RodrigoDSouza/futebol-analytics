import math

import pytest

from futebol_analytics.analysis.quote_check import check_quote


def test_quote_check_shows_break_even_without_claiming_value():
    result = check_quote(2.0, 0.6)
    assert result['probabilidade_equilibrio'] == 0.5
    assert result['diferenca_descritiva_pontos_percentuais'] == pytest.approx(10)
    assert result['vantagem_comprovada'] is False
    assert result['indicacao'] is None


def test_quote_check_rejects_bad_odd_and_handles_missing_benchmark():
    for odd in (1, math.inf, math.nan):
        with pytest.raises(ValueError):
            check_quote(odd, 0.5)
    result = check_quote(1.8, None)
    assert result['diferenca_descritiva_pontos_percentuais'] is None
    assert result['indicacao'] is None
