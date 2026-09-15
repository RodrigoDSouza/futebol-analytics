"""Evoluções do esquema, executadas na transação de inicialização."""

import psycopg


def migrate(connection: psycopg.Connection, *, target: int = 4) -> None:
    # Serializa inicializações concorrentes até o commit/rollback da transação.
    connection.execute("SELECT pg_advisory_xact_lock(7062026)")
    connection.execute("""
        CREATE TABLE IF NOT EXISTS futebol_migracoes (
            versao integer PRIMARY KEY,
            aplicada_em timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    if not connection.execute("SELECT 1 FROM futebol_migracoes WHERE versao = 2").fetchone():
        _version_two(connection)
    if target >= 3 and not connection.execute("SELECT 1 FROM futebol_migracoes WHERE versao = 3").fetchone():
        _version_three(connection)
    if target >= 4 and not connection.execute("SELECT 1 FROM futebol_migracoes WHERE versao = 4").fetchone():
        connection.execute("""
            CREATE TABLE futebol_csv_arquivos (
                id uuid PRIMARY KEY, origem text NOT NULL, temporada text NOT NULL,
                sha256 text NOT NULL, recebido_em timestamptz NOT NULL DEFAULT clock_timestamp(),
                observado_em timestamptz NOT NULL DEFAULT clock_timestamp(),
                csv_original text NOT NULL,
                UNIQUE (origem, temporada, sha256)
            )
        """)
        connection.execute("""
            CREATE TABLE futebol_csv_jogos (
                arquivo_id uuid NOT NULL REFERENCES futebol_csv_arquivos(id),
                data date NOT NULL, mandante text NOT NULL, visitante text NOT NULL,
                estatisticas jsonb NOT NULL,
                PRIMARY KEY (arquivo_id, data, mandante, visitante),
                CHECK (mandante <> visitante)
            )
        """)
        connection.execute("INSERT INTO futebol_migracoes (versao) VALUES (4)")


def _version_two(connection: psycopg.Connection) -> None:
    connection.execute("""
        ALTER TABLE futebol_capturas DROP CONSTRAINT futebol_capturas_recurso_check
    """)
    connection.execute("""
        ALTER TABLE futebol_capturas ADD CONSTRAINT futebol_capturas_recurso_check
        CHECK (recurso IN ('campeonatos', 'partidas', 'tabela', 'estatisticas', 'rodadas', 'artilharia'))
    """)
    connection.execute("INSERT INTO futebol_migracoes (versao) VALUES (2)")


def _version_three(connection: psycopg.Connection) -> None:
    connection.execute("""
        CREATE TABLE futebol_campeonatos (
            origem text NOT NULL, id bigint NOT NULL, temporada text NOT NULL,
            nome text, tipo text, captura_id uuid NOT NULL REFERENCES futebol_capturas(id),
            PRIMARY KEY (origem, id, temporada)
        )
    """)
    connection.execute("""
        CREATE TABLE futebol_times (
            origem text NOT NULL, id bigint NOT NULL, nome text, sigla text,
            captura_id uuid NOT NULL REFERENCES futebol_capturas(id),
            PRIMARY KEY (origem, id)
        )
    """)
    connection.execute("""
        CREATE TABLE futebol_partidas (
            origem text NOT NULL, campeonato_id bigint NOT NULL, temporada text NOT NULL,
            id bigint NOT NULL, rodada integer, mandante_id bigint NOT NULL,
            visitante_id bigint NOT NULL, status text, data_hora timestamptz,
            placar_mandante integer CHECK (placar_mandante >= 0),
            placar_visitante integer CHECK (placar_visitante >= 0),
            captura_id uuid NOT NULL REFERENCES futebol_capturas(id),
            PRIMARY KEY (origem, campeonato_id, temporada, id),
            FOREIGN KEY (origem, campeonato_id, temporada)
                REFERENCES futebol_campeonatos(origem, id, temporada),
            FOREIGN KEY (origem, mandante_id) REFERENCES futebol_times(origem, id),
            FOREIGN KEY (origem, visitante_id) REFERENCES futebol_times(origem, id),
            CHECK (mandante_id <> visitante_id)
        )
    """)
    connection.execute("CREATE INDEX futebol_partidas_data ON futebol_partidas(data_hora)")
    connection.execute("INSERT INTO futebol_migracoes (versao) VALUES (3)")
