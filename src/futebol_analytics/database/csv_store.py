"""Versões do CSV e jogos com estatísticas, sem inferir IDs de outras fontes."""

import hashlib
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from futebol_analytics.api.football_csv import FIELDS, parse_csv, source_url
from futebol_analytics.database.store import SnapshotStore


def import_csv(store: SnapshotStore, content: str, season: str, league: str = "E0") -> dict[str, Any]:
    rows = parse_csv(content, season, league)
    digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
    with store._connection() as connection:
        record = connection.execute("""
            INSERT INTO futebol_csv_arquivos (id, origem, temporada, sha256, csv_original)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (origem, temporada, sha256) DO UPDATE SET observado_em=clock_timestamp()
            RETURNING id
        """, (uuid4(), source_url(season, league), season, digest, content)).fetchone()
        with connection.cursor() as cursor:
            cursor.executemany("""
                INSERT INTO futebol_csv_jogos (arquivo_id, data, mandante, visitante, estatisticas)
                VALUES (%s, %s, %s, %s, %s) ON CONFLICT DO NOTHING
            """, [(record['id'], row['data'], row['mandante'], row['visitante'],
                   Jsonb({field: row[field] for field in FIELDS.values()})) for row in rows])
    return summary(rows) | {"liga": league, "arquivo_id": str(record['id']), "temporada": season,
                            "origem": source_url(season, league), "sha256": digest}


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"jogos": len(rows), "primeira_data": min(r['data'] for r in rows),
            "ultima_data": max(r['data'] for r in rows),
            "cobertura_campos": {field: sum(r[field] is not None for r in rows) for field in FIELDS.values()}}


def read_csv(store: SnapshotStore, season: str, league: str = "E0") -> dict[str, Any]:
    with store._connection() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        record = connection.execute("""
            SELECT id, origem, temporada, recebido_em, observado_em, sha256 FROM futebol_csv_arquivos
            WHERE origem=%s AND temporada=%s ORDER BY observado_em DESC, id DESC LIMIT 1
        """, (source_url(season, league), season)).fetchone()
        if record is None:
            raise ValueError("Nenhum CSV local para essa temporada.")
        records = connection.execute("""
            SELECT data, mandante, visitante, estatisticas FROM futebol_csv_jogos
            WHERE arquivo_id=%s ORDER BY data, mandante, visitante
        """, (record['id'],)).fetchall()
    rows = [dict(data=str(r['data']), mandante=r['mandante'], visitante=r['visitante'], **r['estatisticas']) for r in records]
    return {"arquivo": record, "resumo": summary(rows), "partidas": rows}


def read_csv_original(store: SnapshotStore, season: str, league: str = "E0") -> str:
    with store._connection() as connection:
        record = connection.execute("""
            SELECT csv_original FROM futebol_csv_arquivos
            WHERE origem=%s AND temporada=%s
            ORDER BY observado_em DESC, id DESC LIMIT 1
        """, (source_url(season, league), season)).fetchone()
    if record is None:
        raise ValueError("Nenhum CSV local para essa temporada.")
    return record['csv_original']
