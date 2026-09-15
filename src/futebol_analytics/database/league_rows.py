"""Jogo encerrado do Brasileirão no mesmo contrato de gols dos CSVs europeus."""

from futebol_analytics.database.statistics import DEFAULT_SOURCE
from futebol_analytics.database.store import SnapshotStore
import unicodedata
from datetime import datetime, timedelta


def read_brasileirao_goals(store: SnapshotStore, season: str = '2026') -> dict:
    with store._connection() as connection:
        connection.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        candidates = connection.execute('''SELECT id, nome FROM futebol_campeonatos
            WHERE origem=%s AND temporada=%s''', (DEFAULT_SOURCE, season)).fetchall()
        matches = [r for r in candidates if ''.join(c for c in unicodedata.normalize('NFKD',
                   str(r['nome']).casefold()) if not unicodedata.combining(c))
                   in ('brasileirao serie a', 'campeonato brasileiro serie a')]
        if len(matches) != 1:
            raise ValueError('Brasileirão Série A não localizado de forma única na projeção local.')
        championship_id = matches[0]['id']
        coverage = connection.execute('''
            SELECT count(*) AS jogos, count(*) FILTER (WHERE status='encerrado') AS encerrados,
                   count(*) FILTER (WHERE status='encerrado' AND data_hora IS NOT NULL
                     AND placar_mandante IS NOT NULL AND placar_visitante IS NOT NULL) AS validos,
                   max(c.fim_coleta) AS ultima_coleta
            FROM futebol_partidas p JOIN futebol_capturas c ON c.id=p.captura_id
            WHERE p.origem=%s AND p.campeonato_id=%s AND p.temporada=%s
        ''', (DEFAULT_SOURCE, championship_id, season)).fetchone()
        records = connection.execute('''
            SELECT p.id, (p.data_hora AT TIME ZONE 'America/Sao_Paulo')::date AS data,
                   h.nome AS mandante, a.nome AS visitante,
                   p.placar_mandante AS gols_mandante, p.placar_visitante AS gols_visitante
            FROM futebol_partidas p
            JOIN futebol_times h ON h.origem=p.origem AND h.id=p.mandante_id
            JOIN futebol_times a ON a.origem=p.origem AND a.id=p.visitante_id
            WHERE p.origem=%s AND p.campeonato_id=%s AND p.temporada=%s
              AND p.status='encerrado' AND p.data_hora IS NOT NULL
              AND p.placar_mandante IS NOT NULL AND p.placar_visitante IS NOT NULL
            ORDER BY p.data_hora, p.id
        ''', (DEFAULT_SOURCE, championship_id, season)).fetchall()
    if not coverage['jogos']:
        raise ValueError('Brasileirão não encontrado na projeção local.')
    rows = [dict(data=str(r['data']), mandante=r['mandante'], visitante=r['visitante'],
                 gols_mandante=r['gols_mandante'], gols_visitante=r['gols_visitante'])
            for r in records]
    return {'origem': DEFAULT_SOURCE, 'campeonato_id': championship_id, 'temporada': season,
            'jogos_agenda': coverage['jogos'], 'encerrados': coverage['encerrados'],
            'jogos_validos': len(rows), 'ultima_coleta': str(coverage['ultima_coleta']),
            'partidas': rows}


def read_brasileirao_schedule(store: SnapshotStore, championship_id: int, season: str,
                              now: datetime, days: int = 7) -> list[dict]:
    if now.tzinfo is None or type(days) is not int or not 1 <= days <= 30:
        raise ValueError('Horário com fuso e intervalo de 1 a 30 dias são obrigatórios.')
    with store._connection() as connection:
        records = connection.execute('''
            SELECT p.id, p.data_hora, p.status, h.nome AS mandante, a.nome AS visitante,
                   c.fim_coleta AS agenda_observada_em
            FROM futebol_partidas p
            JOIN futebol_times h ON h.origem=p.origem AND h.id=p.mandante_id
            JOIN futebol_times a ON a.origem=p.origem AND a.id=p.visitante_id
            JOIN futebol_capturas c ON c.id=p.captura_id
            WHERE p.origem=%s AND p.campeonato_id=%s AND p.temporada=%s
              AND p.status='aguardando' AND p.data_hora>%s AND p.data_hora<=%s
            ORDER BY p.data_hora, p.id
        ''', (DEFAULT_SOURCE, championship_id, season, now, now + timedelta(days=days))).fetchall()
    return [dict(r, data_hora=r['data_hora'].isoformat(),
                 agenda_observada_em=r['agenda_observada_em'].isoformat()) for r in records]
