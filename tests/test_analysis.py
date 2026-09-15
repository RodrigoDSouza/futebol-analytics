from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from futebol_analytics.analysis.team import analyze_team
from futebol_analytics.main import main


def match(mid, home=1, away=2, scored=2, conceded=1, **changes):
    result = dict(id=mid, mandante_id=home, visitante_id=away, placar_mandante=scored,
                  placar_visitante=conceded, status="encerrado", captura_id="fixture",
                  data_hora=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=mid),
                  coletado_em=datetime(2026, 9, 1, tzinfo=timezone.utc))
    return result | changes


def test_hand_calculated_results_and_frequencies():
    result = analyze_team([match(1), match(2, home=2, away=1, scored=0, conceded=0),
                           match(3, home=2, away=1, scored=3, conceded=1)], 1)
    assert result["resultados"] == {"vitorias": 1, "empates": 1, "derrotas": 1}
    assert result["gols"] == dict(marcados=3, sofridos=4, media_marcados=1.0,
                                  media_sofridos=1.3333, media_total_por_jogo=2.3333)
    assert result["forma_do_mais_antigo_ao_mais_recente"] == ["V", "E", "D"]
    frequencies = result["frequencias_historicas"]
    assert frequencies["over_2.5"] == {"ocorrencias": 2, "jogos": 3, "percentual": 66.67}
    assert frequencies["over_3.5"]["ocorrencias"] == 1
    assert frequencies["ambas_marcam"]["ocorrencias"] == 2
    assert frequencies["sem_sofrer_gols"]["ocorrencias"] == 1


def test_undated_counts_in_totals_but_not_sequence():
    rows = [match(1), match(2, data_hora=None)]
    totals, recent = analyze_team(rows, 1), analyze_team(rows, 1, last=5)
    assert totals["amostra"]["utilizados"] == 2
    assert totals["forma_do_mais_antigo_ao_mais_recente"] is None
    assert recent["amostra"]["utilizados"] == 1
    assert recent["amostra"]["motivos_exclusao"] == {"sem_data_para_sequencia": 1}
    assert recent["amostra"]["janela_completa"] is False


def test_filters_then_validity_then_recent_window():
    rows = [match(mid) for mid in range(1, 8)] + [match(8, status="aguardando"),
                                               match(9, placar_mandante=None), match(10, data_hora=None)]
    result = analyze_team(list(reversed(rows)), 1, last=5)
    sample = result["amostra"]
    assert sample["encontrados_no_recorte"] == 10
    assert sample["elegiveis"] == 7 and sample["utilizados"] == 5
    assert sample["excluidos_por_criterio"] == 3 and sample["fora_da_janela"] == 2
    assert {m["partida_id"] for m in result["jogos_utilizados"]} == {3, 4, 5, 6, 7}


def test_venue_and_head_to_head():
    rows = [match(1), match(2, home=2, away=1), match(3, home=1, away=3)]
    result = analyze_team(rows, 1, venue="visitante", opponent_id=2)
    assert result["amostra"]["utilizados"] == 1
    assert result["resultados"]["derrotas"] == 1


def test_empty_sample_has_no_invented_rates():
    result = analyze_team([], 1, last=10)
    assert result["gols"]["media_marcados"] is None
    assert result["frequencias_historicas"]["over_0.5"]["percentual"] is None
    assert result["amostra"]["janela_completa"] is False


@pytest.mark.parametrize("value", [None, -1, True])
def test_invalid_score_excluded(value):
    result = analyze_team([match(1, placar_visitante=value)], 1)
    assert result["amostra"]["utilizados"] == 0
    assert result["amostra"]["motivos_exclusao"] == {"placar_incompleto_ou_invalido": 1}


def test_future_result_relative_to_capture_excluded():
    result = analyze_team([match(1, data_hora=datetime(2027, 1, 1, tzinfo=timezone.utc))], 1)
    assert result["amostra"]["motivos_exclusao"] == {"data_posterior_a_coleta": 1}


def test_statistics_cli_never_loads_api_credentials(monkeypatch, capsys):
    monkeypatch.setenv("FUTEBOL_DATABASE_URL", "postgresql://localhost/test")
    with patch("futebol_analytics.main.load_settings", side_effect=AssertionError("Sem API")):
        with patch("futebol_analytics.main.team_report", return_value={"ok": True}):
            assert main(["analisar-time", "1", "--campeonato-id", "3", "--ultimos", "5"]) == 0
    assert '"ok": true' in capsys.readouterr().out
