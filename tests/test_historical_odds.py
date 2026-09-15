from futebol_analytics.analysis.historical_odds import compare_historical_odds


def test_market_probability_removes_margin_and_aligns_fixture():
    csv_text = ('Date,HomeTeam,AwayTeam,B365>2.5,B365<2.5,B365C>2.5,B365C<2.5\n'
                '01/09/2025,A,B,2.00,2.00,1.50,3.00\n')
    predictions = [{'data': '2025-09-01', 'mandante': 'A', 'visitante': 'B',
                    'resultado': 1, 'probabilidade': 0.6, 'baseline_liga': 0.5}]
    result = compare_historical_odds(csv_text, predictions)
    assert result['jogos_avaliados'] == 1
    assert result['brier']['mercado_abertura'] == 0.25
    assert abs(result['brier']['mercado_fechamento'] - (2/3-1)**2) < 1e-12
    assert result['indicacoes'] == []


def test_missing_odds_is_excluded():
    csv_text = ('Date,HomeTeam,AwayTeam,B365>2.5,B365<2.5,B365C>2.5,B365C<2.5\n'
                '01/09/2025,A,B,,2.00,1.50,3.00\n')
    prediction = {'data': '2025-09-01', 'mandante': 'A', 'visitante': 'B',
                  'resultado': 0, 'probabilidade': 0.6, 'baseline_liga': 0.5}
    result = compare_historical_odds(csv_text, [prediction])
    assert result['jogos_avaliados'] == 0
    assert result['previsoes_sem_odds_alinhadas'] == 1
    assert result['brier']['modelo'] is None
