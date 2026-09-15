from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
import os
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
import pytest

from futebol_analytics.config.settings import DatabaseSettings
from futebol_analytics.database.store import SnapshotStore
from futebol_analytics.database.normalized import process_local
from futebol_analytics.database.statistics import list_teams, team_report
from futebol_analytics.database.csv_store import import_csv, read_csv
from futebol_analytics.local_data import build_dataset


def fixtures(matches=None):
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    catalog = dict(id=uuid4(), origem="fixture", recurso="campeonatos", escopo="2026",
                   inicio_coleta=now, fim_coleta=now, gravado_em=now,
                   conteudo={"paginas": [{"data": [{"id": 3, "nome": "Teste", "temporada": "2026",
                                                    "tipo": "pontos-corridos"}]}]})
    match = dict(id=1, time_mandante={"id": 10, "nome": "Time A"},
                 time_visitante={"id": 20, "nome": "Time B"}, status="encerrado",
                 placar_mandante=0, placar_visitante=2, data_hora_realizacao="2026-01-01T20:00:00-03:00")
    rounds = dict(id=uuid4(), origem="fixture", recurso="rodadas", escopo="3",
                  inicio_coleta=now + timedelta(seconds=1), fim_coleta=now + timedelta(seconds=2),
                  gravado_em=now + timedelta(seconds=3),
                  conteudo={"data": [{"numero": 1, "partidas": matches if matches is not None else [match]}]})
    return catalog, rounds


def test_normalization_preserves_zero_timezone_and_provenance():
    catalog, rounds = fixtures()
    result = build_dataset([rounds, catalog])
    assert len(result.matches) == 1 and len(result.teams) == 2
    assert result.matches[0]["placar_mandante"] == 0
    assert result.matches[0]["data_hora"].utcoffset() == timedelta(hours=-3)
    assert result.matches[0]["captura_id"] == rounds["id"]
    assert result.report["ocorrencias"] == {}


@pytest.mark.parametrize("value,code", [(None, "encerrado_sem_placar"), (-1, "placar_invalido"),
                                         (True, "placar_invalido")])
def test_missing_and_invalid_scores(value, code):
    catalog, rounds = fixtures()
    rounds["conteudo"]["data"][0]["partidas"][0]["placar_mandante"] = value
    result = build_dataset([catalog, rounds])
    assert result.matches[0]["placar_mandante"] is None
    assert result.report["ocorrencias"][code] == 1


@pytest.mark.parametrize("conflicting", [False, True])
def test_duplicates_not_silently_overwritten(conflicting):
    catalog, rounds = fixtures()
    matches = rounds["conteudo"]["data"][0]["partidas"]
    duplicate = dict(matches[0])
    if conflicting:
        duplicate["placar_mandante"] = 5
    matches.append(duplicate)
    result = build_dataset([catalog, rounds])
    assert len(result.matches) == (0 if conflicting else 1)
    assert result.report["ocorrencias"]["duplicata_conflitante" if conflicting else "duplicata_identica"] == 1


def test_catalog_after_rounds_not_used_to_guess_season():
    catalog, rounds = fixtures()
    catalog["fim_coleta"] = rounds["fim_coleta"] + timedelta(days=1)
    result = build_dataset([catalog, rounds])
    assert result.matches == []
    assert result.report["ocorrencias"]["rodadas_sem_catalogo_anterior"] == 1


def test_latest_rounds_replace_previous_observation():
    catalog, rounds = fixtures()
    newer = dict(rounds, id=uuid4(), fim_coleta=rounds["fim_coleta"] + timedelta(seconds=1))
    result = build_dataset([catalog, rounds, newer])
    assert len(result.matches) == 1
    assert result.matches[0]["captura_id"] == newer["id"]


@pytest.mark.integration
def test_real_projection_is_repeatable_and_preserves_snapshots():
    url = os.environ.get("FUTEBOL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requer banco PostgreSQL de testes.")
    schema = "test_normalization_" + uuid4().hex
    with psycopg.connect(url, connect_timeout=5) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    store = SnapshotStore(DatabaseSettings(url))

    @contextmanager
    def isolated_connection():
        with psycopg.connect(url, connect_timeout=5, options=f"-c search_path={schema}",
                             row_factory=dict_row) as connection:
            yield connection

    store._connection = isolated_connection
    try:
        store.initialize()
        csv_content = ('Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,HC,AC,HY,AY,HR,AR,HS,AS,HST,AST\n'
                       'E0,21/08/2026,Arsenal,Coventry,3,0,8,2,1,1,0,0,20,4,6,1\n')
        imported = import_csv(store, csv_content, '2026/2027')
        assert import_csv(store, csv_content, '2026/2027')['arquivo_id'] == imported['arquivo_id']
        assert read_csv(store, '2026/2027')['resumo']['jogos'] == 1
        assert read_csv(store, '2026/2027')['partidas'][0]['escanteios_mandante'] == 8
        for capture in fixtures():
            store.save(capture["recurso"], capture["escopo"], capture["origem"], capture["conteudo"],
                       capture["inicio_coleta"], capture["fim_coleta"])
        first = process_local(store, persist=True)
        assert first == process_local(store, persist=True)
        assert len(list_teams(store, 3, "2026", "fixture")) == 2
        analysis = team_report(store, 10, 3, "2026", source="fixture", last=5)
        assert analysis["amostra"]["utilizados"] == 1
        assert analysis["resultados"]["derrotas"] == 1
        assert analysis["gols"]["marcados"] == 0
        assert team_report(store, 10, 3, "2026", source="fixture", venue="visitante")["amostra"]["utilizados"] == 0
        with store._connection() as connection:
            assert connection.execute("SELECT count(*) AS n FROM futebol_partidas").fetchone()["n"] == 1
            assert connection.execute("SELECT count(*) AS n FROM futebol_capturas").fetchone()["n"] == 2
        # Uma falha durante a reconstrução desfaz inclusive os DELETEs anteriores.
        with store._connection() as connection:
            connection.execute("ALTER TABLE futebol_partidas ADD CONSTRAINT fixture_failure CHECK (id <> 1) NOT VALID")
        with pytest.raises(psycopg.errors.CheckViolation):
            process_local(store, persist=True)
        with store._connection() as connection:
            assert connection.execute("SELECT count(*) AS n FROM futebol_partidas").fetchone()["n"] == 1
            assert connection.execute("SELECT count(*) AS n FROM futebol_capturas").fetchone()["n"] == 2
    finally:
        # Remove apenas o schema aleatório criado por este teste no banco dedicado.
        with psycopg.connect(url, connect_timeout=5) as connection:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
