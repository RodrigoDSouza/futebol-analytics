from copy import deepcopy
import pytest
from futebol_analytics.analysis.backtest import backtest
from futebol_analytics.analysis.focus import evaluate_focus


def sample():
    return [dict(data=f'2026-08-{i:02}', mandante='A', visitante='B', gols_mandante=i%3,
                 gols_visitante=1) for i in range(1, 16)]


def test_future_and_target_scores_do_not_change_past_probabilities():
    rows = sample()
    first = backtest(rows)
    changed = deepcopy(rows)
    changed[-1]['gols_mandante'] = 12
    second = backtest(changed)
    assert first['jogos_avaliados'] == 10
    assert [r['probabilidade'] for r in first['previsoes']] == [r['probabilidade'] for r in second['previsoes']]
    assert all(r['ultima_data_treino'] < r['data'] for r in first['previsoes'])


def test_no_sample_and_duplicates():
    assert backtest(sample()[:3])['brier_modelo'] is None
    with pytest.raises(ValueError):
        backtest(sample()+sample()[:1])


def test_calibration_groups_cover_evaluated_games_and_compare_same_targets():
    result = backtest(sample())
    assert sum(group['jogos'] for group in result['calibracao_por_faixa']) == result['jogos_avaliados']
    assert result['supera_baseline_liga'] == (result['brier_modelo'] < result['brier_baseline_liga'])
    assert all(0 <= group['frequencia_observada'] <= 1 for group in result['calibracao_por_faixa'])


def test_both_teams_score_uses_prior_scores_and_zero_goal_rule():
    rows = sample()
    result = backtest(rows, 'ambas_sim')
    assert result['mercado'] == 'ambas_sim'
    assert result['jogos_avaliados'] == 10
    assert all(row['ultima_data_treino'] < row['data'] for row in result['previsoes'])
    assert [row['resultado'] for row in result['previsoes']] == [int(r['gols_mandante'] > 0)
        for r in rows[5:]]
    assert all(0 <= row['baseline_liga'] <= 1 for row in result['previsoes'])


def test_over_one_point_five_counts_two_total_goals():
    rows = sample()
    result = backtest(rows, 'gols_mais_1.5')
    assert result['mercado'] == 'gols_mais_1.5'
    assert [row['resultado'] for row in result['previsoes']] == [
        int(r['gols_mandante'] + r['gols_visitante'] >= 2) for r in rows[5:]]
    assert all(row['ultima_data_treino'] < row['data'] for row in result['previsoes'])


def test_brazilian_evaluation_survives_missing_european_history():
    result = evaluate_focus(None, {'partidas': sample(), 'temporada': '2026'})
    assert set(result['ligas']) == {'brasileirao'}
    assert result['ligas']['brasileirao']['avaliacoes']['gols_mais_1.5']['jogos_avaliados'] == 10
    assert result['indicacoes'] == []
    with pytest.raises(ValueError):
        evaluate_focus(None, None)
