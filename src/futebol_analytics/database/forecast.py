"""Seleção de partidas e amostras para previsão, exclusivamente no banco local."""

from datetime import datetime, timezone
from typing import Any

from futebol_analytics.database.statistics import DEFAULT_SOURCE
from futebol_analytics.database.store import SnapshotStore
from futebol_analytics.models.poisson import predict


def upcoming(store: SnapshotStore, championship_id: int, season: str, source: str = DEFAULT_SOURCE) -> list[dict[str, Any]]:
    with store._connection() as connection:
        return connection.execute("""
            SELECT p.id, p.data_hora, h.nome AS mandante, a.nome AS visitante, c.fim_coleta AS agenda_observada_em
            FROM futebol_partidas p
            JOIN futebol_times h ON h.origem=p.origem AND h.id=p.mandante_id
            JOIN futebol_times a ON a.origem=p.origem AND a.id=p.visitante_id
            JOIN futebol_capturas c ON c.id=p.captura_id
            WHERE p.origem=%s AND p.campeonato_id=%s AND p.temporada=%s
              AND p.status='aguardando' AND p.data_hora > %s
            ORDER BY p.data_hora, p.id LIMIT 20
        """, (source, championship_id, season, datetime.now(timezone.utc))).fetchall()


def forecast(store: SnapshotStore, match_id: int, championship_id: int, season: str,
             source: str = DEFAULT_SOURCE, *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    with store._connection() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        rows = connection.execute("""
            SELECT p.*, c.fim_coleta AS coletado_em FROM futebol_partidas p
            JOIN futebol_capturas c ON c.id=p.captura_id
            WHERE p.origem=%s AND p.campeonato_id=%s AND p.temporada=%s ORDER BY p.id
        """, (source, championship_id, season)).fetchall()
        target = next((m for m in rows if m["id"] == match_id), None)
        if target is None:
            raise ValueError("Partida não encontrada no campeonato/temporada local.")
        names = connection.execute("""
            SELECT id, nome FROM futebol_times WHERE origem=%s AND id IN (%s, %s)
        """, (source, target["mandante_id"], target["visitante_id"])).fetchall()
    report = predict(target, rows, now=now)
    labels = {r["id"]: r["nome"] for r in names}
    report["partida"].update(mandante=labels.get(target["mandante_id"]), visitante=labels.get(target["visitante_id"]))
    return report
