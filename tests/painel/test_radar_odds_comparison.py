import pytest
from futebol_painel.analysis.odds import comparar_frequencia_odd

def test_compare():
    result = comparar_frequencia_odd(60, 1.57)
    assert result['equilibrio_percentual'] == pytest.approx(100/1.57)
    assert result['diferenca_pontos_percentuais'] < 0

@pytest.mark.parametrize('frequency,odd', [(101,1.5),(60,1),(float('nan'),1.5),(70,float('inf'))])
def test_invalid(frequency,odd):
    with pytest.raises(ValueError):
        comparar_frequencia_odd(frequency,odd)
