from datetime import datetime, timedelta, timezone
import math
from unittest.mock import patch

import pytest

from futebol_analytics.models.poisson import markets, poisson_distribution, predict
from futebol_analytics.main import main


def sample():
    now = datetime(2026, 9, 8, tzinfo=timezone.utc)
    rows = [dict(id=i, origem="fixture", campeonato_id=3, temporada="2026",
                 mandante_id=1 if i <= 10 else 4, visitante_id=3 if i <= 10 else 2,
                 status="encerrado", placar_mandante=2, placar_visitante=1,
                 data_hora=now - timedelta(days=30-i), coletado_em=now - timedelta(days=1),
                 captura_id="fixture") for i in range(1, 21)]
    target = dict(rows[0], id=100, mandante_id=1, visitante_id=2, status="aguardando",
                  placar_mandante=None, placar_visitante=None, data_hora=now+timedelta(days=4))
    return now, target, rows


@pytest.mark.parametrize("mean", [0, 0.1, 1, 2, 10, 20])
def test_distribution_mass_and_known_pmf(mean):
    values = poisson_distribution(mean)
    assert abs(sum(values)-1) < 1.1e-12
    assert values[0] == pytest.approx(math.exp(-mean))
    if mean > 0:
        assert values[2] == pytest.approx(math.exp(-mean)*mean**2/2)


@pytest.mark.parametrize("mean", [-1, 21, float("inf"), float("nan")])
def test_invalid_mean_rejected(mean):
    with pytest.raises(ValueError):
        poisson_distribution(mean)


def test_markets_against_analytical_results():
    result = markets(2, 1)
    p = result["probabilidades"]
    assert p["mandante"]+p["empate"]+p["visitante"] == pytest.approx(1)
    assert p["ambas_marcam"] == pytest.approx((1-math.exp(-2))*(1-math.exp(-1)), abs=3e-12)
    assert p["over_0.5"] == pytest.approx(1-math.exp(-3), abs=3e-12)
    assert p["over_0.5"] >= p["over_1.5"] >= p["over_2.5"] >= p["over_3.5"]
    assert all(0 <= value <= 1 for value in p.values())
    assert result["precisao_numerica"]["massa_omitida_antes_normalizacao"] <= 2.1e-12


def test_equal_strength_symmetry_and_degenerate_case():
    p = markets(1, 1)["probabilidades"]
    assert p["mandante"] == pytest.approx(p["visitante"])
    p = markets(0, 0)["probabilidades"]
    assert p["empate"] == 1 and p["ambas_marcam"] == 0 and p["over_0.5"] == 0


def test_rates_hand_calculated_and_target_excluded():
    now, target, rows = sample()
    report = predict(target, rows+[target], now=now)
    assert report["gols_esperados_modelo"] == {"mandante": 2, "visitante": 1}
    assert report["amostra"]["liga"] == 20
    assert report["amostra"]["mandante_em_casa"] == report["amostra"]["visitante_fora"] == 10
    assert report["amostra"]["motivos"] == {"partida_alvo": 1}
    assert report["confianca"] is None
    assert predict(target, list(reversed(rows))+[target], now=now)["amostra"]["sha256_dados"] == report["amostra"]["sha256_dados"]


def test_invalid_rows_do_not_change_expected_goals():
    now, target, rows = sample()
    extras = [dict(rows[0], id=90, data_hora=None),
              dict(rows[0], id=91, placar_mandante=None),
              dict(rows[0], id=92, coletado_em=now+timedelta(days=1)),
              dict(rows[0], id=93, data_hora=now+timedelta(days=1))]
    report = predict(target, rows+extras, now=now)
    assert report["gols_esperados_modelo"] == {"mandante": 2, "visitante": 1}
    assert report["amostra"]["excluidos"] == 4


def test_insufficient_sample_abstains():
    now, target, rows = sample()
    with pytest.raises(ValueError, match="insuficiente"):
        predict(target, rows[:10], now=now)


def test_dixon_coles_preserves_probability_mass_and_changes_low_scores():
    from futebol_analytics.models.poisson import markets
    independent = markets(1.4, 1.0)
    corrected = markets(1.4, 1.0, rho=-.08)
    assert sum(corrected["probabilidades"][key] for key in
               ("mandante", "empate", "visitante")) == pytest.approx(1)
    assert corrected["probabilidades"]["empate"] != independent["probabilidades"]["empate"]
    assert corrected["precisao_numerica"]["rho_dixon_coles"] == -.08


@pytest.mark.parametrize("change", [{"status":"encerrado"}, {"data_hora":None},
    {"data_hora":datetime(2026, 1, 1, tzinfo=timezone.utc)}])
def test_no_retrospective_predictions(change):
    now, target, rows = sample()
    with pytest.raises(ValueError):
        predict(target | change, rows, now=now)


def test_mixed_competitions_and_duplicate_rows_rejected():
    now, target, rows = sample()
    with pytest.raises(ValueError, match="mistura"):
        predict(target, rows+[dict(rows[0], id=90, campeonato_id=4)], now=now)
    with pytest.raises(ValueError, match="duplicados"):
        predict(target, rows+[rows[0]], now=now)


def test_cli_forecast_never_loads_api_credentials(monkeypatch, capsys):
    monkeypatch.setenv("FUTEBOL_DATABASE_URL", "postgresql://localhost/test")
    with patch("futebol_analytics.main.load_settings", side_effect=AssertionError("Sem API")):
        with patch("futebol_analytics.main.forecast", return_value={"modelo":"poisson_v1"}):
            assert main(["prever-partida", "100", "--campeonato-id", "3"]) == 0
    assert "poisson_v1" in capsys.readouterr().out
