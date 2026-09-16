import pytest

from futebol_analytics.analysis.calibration import calibration_report, grouped_calibration


def test_calibration_reports_brier_log_loss_and_weighted_error():
    rows = [{"mercado": "totals", "selecao": "over", "linha": 1.5,
             "probabilidade": probability, "resultado": result}
            for probability, result in ((.2, 0), (.4, 1), (.7, 1), (.8, 1))]
    report = calibration_report(rows)
    assert report["avaliadas"] == 4
    assert report["brier"] == pytest.approx((.04 + .36 + .09 + .04) / 4)
    assert report["log_loss"] > 0
    assert 0 <= report["erro_calibracao"] <= 1
    assert sum(item["previsoes"] for item in report["faixas"]) == 4


def test_calibration_handles_empty_sample_and_groups_markets():
    assert calibration_report([])["brier"] is None
    rows = [{"mercado": "btts", "selecao": "sim", "linha": 0,
             "probabilidade": .6, "resultado": 1},
            {"mercado": "totals", "selecao": "over", "linha": 2.5,
             "probabilidade": .4, "resultado": 0}]
    assert len(grouped_calibration(rows)) == 2
