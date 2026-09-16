"""Versões do CSV e jogos com estatísticas, sem inferir IDs de outras fontes."""

import hashlib
import json
from typing import Any
from uuid import uuid4

from psycopg.types.json import Jsonb

from futebol_analytics.api.football_csv import FIELDS, parse_csv, source_url
from futebol_analytics.database.store import SnapshotStore


FOOTBALL_DATA_API_ORIGIN = 'https://api.football-data.org/v4/competitions/PL/matches'


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


def import_premier_api(store: SnapshotStore, capture: dict[str, Any], season: str) -> dict[str, Any]:
    """Persiste placares licenciados da football-data.org no contrato histórico existente."""
    if (capture.get('provedor') != 'football-data' or capture.get('competicao') != 'PL'
            or capture.get('temporada_inicio') != int(season[:4])):
        raise ValueError('Captura da Premier incompatível com a temporada.')
    rows = []
    for game in capture.get('jogos', []):
        score = game.get('score', {}).get('fullTime', {})
        home, away = score.get('home'), score.get('away')
        if game.get('status') != 'FINISHED' or type(home) is not int or type(away) is not int:
            continue
        row = {field: None for field in FIELDS.values()}
        row.update(data=game['utcDate'][:10], mandante=game['homeTeam']['name'],
                   visitante=game['awayTeam']['name'], gols_mandante=home, gols_visitante=away)
        rows.append(row)
    keys = [(row['data'], row['mandante'], row['visitante']) for row in rows]
    if not rows or len(keys) != len(set(keys)):
        raise ValueError('Captura da Premier sem jogos encerrados ou com duplicidades.')
    content = json.dumps(capture, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
    with store._connection() as connection:
        record = connection.execute("""
            INSERT INTO futebol_csv_arquivos (id, origem, temporada, sha256, csv_original)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (origem, temporada, sha256) DO UPDATE SET observado_em=clock_timestamp()
            RETURNING id
        """, (uuid4(), FOOTBALL_DATA_API_ORIGIN, season, digest, content)).fetchone()
        columns = ('arquivo_id', 'data', 'mandante', 'visitante', 'estatisticas')
        values = [(record['id'], row['data'], row['mandante'], row['visitante'],
                   Jsonb({field: row[field] for field in FIELDS.values()})) for row in rows]
        for start in range(0, len(values), 100):
            batch = values[start:start + 100]
            placeholders = ','.join('(' + ','.join(['%s'] * len(columns)) + ')' for _ in batch)
            connection.execute(f"""INSERT INTO futebol_csv_jogos ({','.join(columns)})
                VALUES {placeholders} ON CONFLICT DO NOTHING""",
                tuple(value for item in batch for value in item))
    return summary(rows) | {'liga': 'E0', 'arquivo_id': str(record['id']), 'temporada': season,
                            'origem': FOOTBALL_DATA_API_ORIGIN, 'sha256': digest}


def read_csv(store: SnapshotStore, season: str, league: str = "E0") -> dict[str, Any]:
    with store._connection() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        if league == 'E0':
            record = connection.execute("""
                SELECT id, origem, temporada, recebido_em, observado_em, sha256 FROM futebol_csv_arquivos
                WHERE origem IN (%s, %s) AND temporada=%s
                ORDER BY (origem=%s) DESC, observado_em DESC, id DESC LIMIT 1
            """, (FOOTBALL_DATA_API_ORIGIN, source_url(season, league), season,
                  FOOTBALL_DATA_API_ORIGIN)).fetchone()
        else:
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
