import os
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

import psycopg
import pytest

from futebol_analytics.config.settings import ConfigurationError, DatabaseSettings, load_database_settings
from futebol_analytics.database.store import DatabaseError, SnapshotStore
from futebol_analytics.database.migrations import migrate
from futebol_analytics.main import main


def test_database_configuration_without_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("DADOS_FUTEBOL_API_KEY", raising=False)
    monkeypatch.setenv("FUTEBOL_DATABASE_URL", "postgresql://localhost/test")
    assert load_database_settings(tmp_path / "missing").url.endswith("/test")


@pytest.mark.parametrize("url", ["", "sqlite:///test", "postgresql://localhost", "postgresql://localhost:bad/test"])
def test_invalid_database_configuration(url):
    with pytest.raises(ConfigurationError):
        DatabaseSettings(url)


def test_database_error_does_not_expose_driver_details():
    with patch("futebol_analytics.database.store.psycopg.connect", side_effect=psycopg.OperationalError("private-details")):
        with pytest.raises(DatabaseError) as error:
            SnapshotStore(DatabaseSettings("postgresql://localhost/test")).initialize()
    assert "private-details" not in str(error.value)


def test_local_cli_does_not_load_api_settings(monkeypatch, capsys):
    monkeypatch.setenv("FUTEBOL_DATABASE_URL", "postgresql://localhost/test")
    with patch("futebol_analytics.main.load_settings", side_effect=AssertionError("API não deveria ser usada")):
        with patch("futebol_analytics.main.SnapshotStore") as store:
            store.return_value.history.return_value = []
            assert main(["historico", "partidas", "77"]) == 0
    assert capsys.readouterr().out.strip() == "[]"


@pytest.mark.integration
def test_postgres_roundtrip_history_and_rollback():
    url = os.environ.get("FUTEBOL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina FUTEBOL_TEST_DATABASE_URL para um banco de testes dedicado.")
    store = SnapshotStore(DatabaseSettings(url))
    store.initialize()
    store.initialize()
    scope = "test-" + uuid4().hex
    now = datetime.now(timezone.utc)
    try:
        first = store.save("partidas", scope, "fixture", {"data": [{"id": 1, "placar": None}]}, now, now)
        second = store.save("partidas", scope, "fixture", {"data": [{"id": 1, "placar": 2}]}, now, now)
        assert store.read("partidas", scope)["id"] == second
        assert store.read("partidas", scope, snapshot_id=first)["conteudo"]["data"][0]["placar"] is None
        assert len(store.history("partidas", scope)) == 2
        with pytest.raises(DatabaseError):
            with store._connection() as connection:
                connection.execute("DELETE FROM futebol_capturas WHERE escopo = %s", (scope,))
                connection.execute("SELECT 1 / 0")
        assert len(store.history("partidas", scope)) == 2
    finally:
        with psycopg.connect(url, connect_timeout=5) as connection:
            connection.execute("DELETE FROM futebol_capturas WHERE escopo = %s", (scope,))


@pytest.mark.integration
def test_migration_preserves_existing_rows_and_runs_once():
    url = os.environ.get("FUTEBOL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Defina FUTEBOL_TEST_DATABASE_URL para um banco de testes dedicado.")
    with psycopg.connect(url, connect_timeout=5) as connection:
        # Tabelas temporárias isolam o teste da migração das tabelas persistentes.
        connection.execute("""
            CREATE TEMP TABLE futebol_capturas (
                recurso text CHECK (recurso IN ('campeonatos', 'partidas', 'tabela', 'estatisticas'))
            ) ON COMMIT DROP
        """)
        connection.execute("""
            CREATE TEMP TABLE futebol_migracoes (
                versao integer PRIMARY KEY, aplicada_em timestamptz DEFAULT now()
            ) ON COMMIT DROP
        """)
        connection.execute("INSERT INTO futebol_capturas VALUES ('tabela')")
        migrate(connection, target=2)
        migrate(connection, target=2)
        connection.execute("INSERT INTO futebol_capturas VALUES ('rodadas'), ('artilharia')")
        assert connection.execute("SELECT recurso FROM futebol_capturas ORDER BY recurso").fetchall() == [
            ('artilharia',), ('rodadas',), ('tabela',)]
        assert connection.execute("SELECT count(*) FROM futebol_migracoes").fetchone()[0] == 1
