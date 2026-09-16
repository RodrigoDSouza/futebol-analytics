"""Histórico de coletas completas, separado do cliente HTTP."""

from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator
from uuid import UUID, uuid4
from urllib.parse import urlsplit

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from futebol_analytics.config.settings import DatabaseSettings
from futebol_analytics.database.migrations import migrate
from futebol_analytics.database.neon_http import NeonHttpConnection, NeonHttpError

RESOURCES = ("campeonatos", "partidas", "tabela", "estatisticas", "rodadas", "artilharia")


class DatabaseError(Exception):
    """Falha de persistência com mensagem segura para o terminal."""


class SnapshotStore:
    def __init__(self, settings: DatabaseSettings) -> None:
        self._settings = settings

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection]:
        try:
            if (urlsplit(self._settings.url).hostname or "").endswith(".neon.tech"):
                with NeonHttpConnection(self._settings.url) as connection:
                    yield connection
                return
            with psycopg.connect(self._settings.url, connect_timeout=5,
                                 options="-c statement_timeout=30000", row_factory=dict_row) as connection:
                yield connection
        except (psycopg.Error, NeonHttpError):
            raise DatabaseError(
                "Falha no PostgreSQL. Verifique o serviço, a configuração e se banco-iniciar foi executado."
            ) from None

    def initialize(self) -> None:
        """Cria o esquema inicial e aplica migrações preservando as capturas."""
        with self._connection() as connection:
            connection.execute("SELECT pg_advisory_xact_lock(7062026)")
            connection.execute("""
                CREATE TABLE IF NOT EXISTS futebol_capturas (
                    id uuid PRIMARY KEY,
                    recurso text NOT NULL CHECK (recurso IN ('campeonatos', 'partidas', 'tabela', 'estatisticas')),
                    escopo text NOT NULL,
                    origem text NOT NULL,
                    inicio_coleta timestamptz NOT NULL,
                    fim_coleta timestamptz NOT NULL,
                    gravado_em timestamptz NOT NULL DEFAULT clock_timestamp(),
                    conteudo jsonb NOT NULL CHECK (jsonb_typeof(conteudo) = 'object'),
                    CHECK (fim_coleta >= inicio_coleta)
                )
            """)
            connection.execute("""
                CREATE INDEX IF NOT EXISTS futebol_capturas_busca
                ON futebol_capturas (recurso, escopo, fim_coleta DESC, gravado_em DESC, id DESC)
            """)
            migrate(connection)

    def save(self, resource: str, scope: str, source: str, payload: dict[str, Any],
             started_at: datetime, finished_at: datetime) -> UUID:
        if resource not in RESOURCES or not scope or not source:
            raise ValueError("Recurso, escopo ou origem inválidos para a captura.")
        if (started_at.tzinfo is None or finished_at.tzinfo is None or finished_at < started_at):
            raise ValueError("A captura exige horários com fuso e intervalo válido.")
        snapshot_id = uuid4()
        with self._connection() as connection:
            connection.execute("""
                INSERT INTO futebol_capturas
                    (id, recurso, escopo, origem, inicio_coleta, fim_coleta, conteudo)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (snapshot_id, resource, scope, source, started_at, finished_at, Jsonb(payload)))
        return snapshot_id

    def read(self, resource: str, scope: str, *, snapshot_id: UUID | None = None) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute("""
                SELECT * FROM futebol_capturas
                WHERE recurso = %s AND escopo = %s AND (%s::uuid IS NULL OR id = %s::uuid)
                ORDER BY fim_coleta DESC, gravado_em DESC, id DESC LIMIT 1
            """, (resource, scope, snapshot_id, snapshot_id)).fetchone()
        if row is None:
            raise DatabaseError("Nenhuma captura local encontrada para esse recurso e escopo.")
        return row

    def history(self, resource: str, scope: str, *, limit: int = 20) -> list[dict[str, Any]]:
        if not 1 <= limit <= 100:
            raise ValueError("O limite do histórico deve estar entre 1 e 100.")
        with self._connection() as connection:
            return connection.execute("""
                SELECT id, recurso, escopo, origem, inicio_coleta, fim_coleta, gravado_em
                FROM futebol_capturas WHERE recurso = %s AND escopo = %s
                ORDER BY fim_coleta DESC, gravado_em DESC, id DESC LIMIT %s
            """, (resource, scope, limit)).fetchall()
