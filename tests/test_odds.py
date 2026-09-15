from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from futebol_analytics.analysis.odds import evaluate

NOW = datetime(2026, 9, 14, 15, tzinfo=timezone.utc)


def quote(mid=1, market="mandante"):
    return dict(partida_id=mid, campeonato_id=3, temporada="2026", mandante="Bahia", visitante="Remo",
                data_hora="2026-09-14T20:00:00-03:00", observado_em=NOW.isoformat(),
                mercado=market, periodo="tempo_regulamentar", odd=1.5, url="https://www.betano.bet.br/")


def forecast(mid, cid, season):
    return dict(partida=dict(id=mid, campeonato_id=cid, temporada=season, mandante="Bahia", visitante="Remo",
                            data_hora="2026-09-14T23:00:00+00:00"), calculado_em=NOW.isoformat(),
                agenda_observada_em=NOW.isoformat(), amostra=dict(ultima_coleta_utilizada=NOW.isoformat()),
                probabilidades=dict(mandante=.7, over_1_5=.8, empate=.2))


def test_value_and_max_three_distinct_games():
    rows = [quote(i) for i in range(1, 6)]
    result = evaluate(rows, forecast, now=NOW)
    assert len(result["candidatos_experimentais"]) == 3
    pick = result["candidatos_experimentais"][0]
    assert pick["valor_esperado_por_real_modelo"] == pytest.approx(.05)
    assert pick["probabilidade_equilibrio"] == pytest.approx(2/3)


@pytest.mark.parametrize("changes", [
    {"odd": float("nan")}, {"odd": True}, {"odd": 1.7},
    {"mercado": "escanteios"}, {"periodo": "primeiro_tempo"},
    {"observado_em": (NOW - timedelta(minutes=16)).isoformat()},
    {"observado_em": (NOW + timedelta(minutes=1)).isoformat()},
    {"observado_em": "2026-09-14T15:00:00"},
    {"data_hora": "2026-09-15T23:00:00+00:00"},
    {"mandante": "Remo", "visitante": "Bahia"},
    {"url": "https://betano.bet.br.example.com/"},
    {"url": "https://user:password@betano.bet.br/"},
    {"partida_id": True}, {"mercado": "empate"},
])
def test_rejects_invalid_or_unprofitable(changes):
    row = quote()
    row.update(changes)
    result = evaluate([row], forecast, now=NOW)
    assert not result["candidatos_experimentais"]
    assert len(result["rejeitadas"]) == 1


def test_stale_base():
    def old(*args):
        report = forecast(*args)
        report["agenda_observada_em"] = (NOW - timedelta(days=2)).isoformat()
        return report
    assert "Agenda" in evaluate([quote()], old, now=NOW)["rejeitadas"][0]["motivo"]


def test_duplicates_are_all_rejected():
    row = quote()
    second = deepcopy(row)
    second["odd"] = 1.55
    result = evaluate([row, second], forecast, now=NOW)
    assert not result["candidatos_experimentais"]
    assert len(result["rejeitadas"]) == 2


def test_multiple_markets_choose_one_game_and_cache_forecast():
    calls = []
    def model(*args):
        calls.append(args)
        report = forecast(*args)
        report["probabilidades"]["over_1.5"] = .8
        return report
    result = evaluate([quote(), quote(market="over_1.5")], model, now=NOW)
    assert len(calls) == 1
    assert len(result["candidatos_experimentais"]) == 1
    assert result["candidatos_experimentais"][0]["cotacao"]["mercado"] == "over_1.5"


def test_no_forced_pick():
    assert evaluate([], forecast, now=NOW)["candidatos_experimentais"] == []


def test_local_date_not_utc_date():
    now = datetime(2026, 9, 15, 0, tzinfo=timezone.utc)
    row = quote()
    row.update(data_hora="2026-09-14T23:00:00-03:00", observado_em=now.isoformat())
    def model(*args):
        report = forecast(*args)
        report["partida"]["data_hora"] = row["data_hora"]
        report["calculado_em"] = now.isoformat()
        return report
    assert len(evaluate([row], model, now=now)["candidatos_experimentais"]) == 1
