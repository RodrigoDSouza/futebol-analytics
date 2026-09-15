"""Migra apenas capturas e tabelas brasileiras para PostgreSQL hospedado."""

import argparse
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from dotenv import dotenv_values

from futebol_analytics.config.settings import ConfigurationError, load_database_settings, DatabaseSettings
from futebol_analytics.database.store import DatabaseError, SnapshotStore


TABLES = ('futebol_capturas', 'futebol_campeonatos', 'futebol_times', 'futebol_partidas')
SOURCE = 'https://api.dadosfutebol.com.br'


def validate_hosted_url(value: str) -> DatabaseSettings:
    parsed = urlsplit(value)
    sslmode = parse_qs(parsed.query).get('sslmode', [])
    if parsed.hostname in (None, 'localhost', '127.0.0.1', '::1') or sslmode != ['require']:
        raise ValueError('O destino deve ser remoto e incluir sslmode=require.')
    return DatabaseSettings(value)


def copy_table(source, destination, table: str) -> int:
    with source.cursor() as cursor:
        cursor.execute(sql.SQL('SELECT * FROM {} WHERE origem = %s').format(sql.Identifier(table)), (SOURCE,))
        rows = cursor.fetchall()
        columns = [column.name for column in cursor.description]
    if not rows:
        return 0
    query = sql.SQL('INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING').format(
        sql.Identifier(table), sql.SQL(', ').join(map(sql.Identifier, columns)),
        sql.SQL(', ').join(sql.Placeholder() for _ in columns))
    values = [tuple(Jsonb(row[name]) if isinstance(row[name], (dict, list)) else row[name]
                    for name in columns) for row in rows]
    with destination.cursor() as cursor:
        cursor.executemany(query, values)
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description='Migração seletiva de dados brasileiros; CSV europeu excluído')
    parser.add_argument('--env-local', type=Path, default=Path('.env'))
    parser.add_argument('--executar', action='store_true', help='Sem esta opção, apenas mostra quantidades locais')
    args = parser.parse_args()
    stage = 'origem'
    try:
        local = load_database_settings(args.env_local)
        with psycopg.connect(local.url, row_factory=dict_row, connect_timeout=5) as source:
            source.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            counts = {table: source.execute(sql.SQL('SELECT count(*) AS n FROM {} WHERE origem=%s').format(
                sql.Identifier(table)), (SOURCE,)).fetchone()['n'] for table in TABLES}
            print('Linhas brasileiras locais: ' + ', '.join(f'{table}={n}' for table, n in counts.items()))
            if not args.executar:
                return 0
            values = {**dotenv_values(args.env_local, interpolate=False), **os.environ}
            hosted = validate_hosted_url((values.get('FUTEBOL_HOSTED_DATABASE_URL') or
                                         values.get('DATABASE_URL_UNPOOLED') or '').strip())
            stage = 'esquema_destino'
            target_store = SnapshotStore(hosted)
            target_store.initialize()
            stage = 'dados_destino'
            with psycopg.connect(hosted.url, row_factory=dict_row, connect_timeout=10) as destination:
                for table in TABLES:
                    copy_table(source, destination, table)
                target_counts = {table: destination.execute(sql.SQL(
                    'SELECT count(*) AS n FROM {} WHERE origem=%s').format(sql.Identifier(table)),
                    (SOURCE,)).fetchone()['n'] for table in TABLES}
            print('Linhas brasileiras no destino: ' + ', '.join(
                f'{table}={n}' for table, n in target_counts.items()))
        return 0
    except (ConfigurationError, DatabaseError, psycopg.Error, OSError, ValueError) as error:
        code = getattr(error, 'sqlstate', None)
        print(f'Migração não concluída em {stage}: {type(error).__name__}' +
              (f' (SQLSTATE {code})' if code else '') + '. Nenhum segredo foi exibido.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
