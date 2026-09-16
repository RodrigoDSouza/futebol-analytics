"""Evoluções do esquema, executadas na transação de inicialização."""

import psycopg


def migrate(connection: psycopg.Connection, *, target: int = 5) -> None:
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
    if target >= 5 and not connection.execute("SELECT 1 FROM futebol_migracoes WHERE versao = 5").fetchone():
        _version_five(connection)


def _version_five(connection: psycopg.Connection) -> None:
    """Odds compactas permanentes e detalhes com retenção limitada."""
    connection.execute("""
        CREATE TABLE futebol_odds_eventos (
            provedor text NOT NULL, liga text NOT NULL, evento_id text NOT NULL,
            inicio timestamptz NOT NULL, mandante text NOT NULL, visitante text NOT NULL,
            atualizado_em timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (provedor, liga, evento_id),
            CHECK (mandante <> visitante)
        )
    """)
    connection.execute("""
        CREATE TABLE futebol_odds_capturas (
            id uuid PRIMARY KEY, provedor text NOT NULL,
            capturado_em timestamptz NOT NULL, expira_em timestamptz NOT NULL,
            conteudo jsonb NOT NULL CHECK (jsonb_typeof(conteudo) = 'object'),
            CHECK (expira_em > capturado_em)
        )
    """)
    connection.execute("CREATE INDEX futebol_odds_capturas_expira ON futebol_odds_capturas(expira_em)")
    connection.execute("""
        CREATE TABLE futebol_odds_detalhes (
            provedor text NOT NULL, liga text NOT NULL, evento_id text NOT NULL,
            capturado_em timestamptz NOT NULL, casa text NOT NULL,
            mercado text NOT NULL, selecao text NOT NULL, linha numeric NOT NULL DEFAULT 0,
            odd numeric NOT NULL CHECK (odd > 1),
            FOREIGN KEY (provedor, liga, evento_id)
                REFERENCES futebol_odds_eventos(provedor, liga, evento_id) ON DELETE CASCADE,
            PRIMARY KEY (provedor, liga, evento_id, capturado_em, casa, mercado, selecao, linha)
        )
    """)
    connection.execute("CREATE INDEX futebol_odds_detalhes_tempo ON futebol_odds_detalhes(capturado_em)")
    connection.execute("""
        CREATE TABLE futebol_odds_consensos (
            provedor text NOT NULL, liga text NOT NULL, evento_id text NOT NULL,
            checkpoint text NOT NULL CHECK (checkpoint IN ('abertura', '24h', 'fechamento')),
            mercado text NOT NULL, selecao text NOT NULL, linha numeric NOT NULL DEFAULT 0,
            observado_em timestamptz NOT NULL, casas integer NOT NULL CHECK (casas > 0),
            odd_mediana numeric NOT NULL CHECK (odd_mediana > 1),
            odd_melhor numeric NOT NULL CHECK (odd_melhor > 1),
            probabilidade_justa numeric CHECK (probabilidade_justa > 0 AND probabilidade_justa < 1),
            FOREIGN KEY (provedor, liga, evento_id)
                REFERENCES futebol_odds_eventos(provedor, liga, evento_id) ON DELETE CASCADE,
            PRIMARY KEY (provedor, liga, evento_id, checkpoint, mercado, selecao, linha)
        )
    """)
    connection.execute("""
        CREATE TABLE futebol_previsoes (
            id uuid PRIMARY KEY, provedor text NOT NULL, liga text NOT NULL, evento_id text NOT NULL,
            calculado_em timestamptz NOT NULL, modelo text NOT NULL, versao text NOT NULL,
            mercado text NOT NULL, selecao text NOT NULL, linha numeric NOT NULL DEFAULT 0,
            probabilidade numeric NOT NULL CHECK (probabilidade > 0 AND probabilidade < 1),
            resultado smallint CHECK (resultado IN (0, 1)), avaliado_em timestamptz,
            evidencia jsonb NOT NULL DEFAULT '{}'::jsonb,
            FOREIGN KEY (provedor, liga, evento_id)
                REFERENCES futebol_odds_eventos(provedor, liga, evento_id) ON DELETE CASCADE,
            UNIQUE (provedor, liga, evento_id, modelo, versao, mercado, selecao, linha)
        )
    """)
    connection.execute("CREATE INDEX futebol_previsoes_avaliacao ON futebol_previsoes(avaliado_em, calculado_em)")
    connection.execute("INSERT INTO futebol_migracoes (versao) VALUES (5)")


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
