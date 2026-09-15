"""Leitura local para o motor estatístico; não faz consultas HTTP."""

from typing import Any

from futebol_analytics.analysis.team import analyze_team
from futebol_analytics.database.store import SnapshotStore

DEFAULT_SOURCE = "https://api.dadosfutebol.com.br"


def list_teams(store: SnapshotStore, championship_id: int, season: str,
               source: str = DEFAULT_SOURCE) -> list[dict[str, Any]]:
    with store._connection() as connection:
        return connection.execute("""
            SELECT t.id, t.nome, t.sigla FROM futebol_times t
            WHERE t.origem = %s AND EXISTS (
                SELECT 1 FROM futebol_partidas p
                WHERE p.origem = t.origem AND p.campeonato_id = %s AND p.temporada = %s
                  AND (p.mandante_id = t.id OR p.visitante_id = t.id)
            ) ORDER BY t.nome, t.id
        """, (source, championship_id, season)).fetchall()


def team_report(store: SnapshotStore, team_id: int, championship_id: int, season: str, *,
                last: int | None = None, venue: str = "todos", opponent_id: int | None = None,
                source: str = DEFAULT_SOURCE) -> dict[str, Any]:
    with store._connection() as connection:
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        team = connection.execute("SELECT id, nome FROM futebol_times WHERE origem = %s AND id = %s",
                                  (source, team_id)).fetchone()
        championship = connection.execute("""
            SELECT id, nome, temporada FROM futebol_campeonatos
            WHERE origem = %s AND id = %s AND temporada = %s
        """, (source, championship_id, season)).fetchone()
        if team is None or championship is None:
            raise ValueError("Time ou campeonato/temporada não encontrado na base normalizada local.")
        matches = connection.execute("""
            SELECT p.*, c.fim_coleta AS coletado_em FROM futebol_partidas p
            JOIN futebol_capturas c ON c.id = p.captura_id
            WHERE p.origem = %s AND p.campeonato_id = %s AND p.temporada = %s
              AND (p.mandante_id = %s OR p.visitante_id = %s)
            ORDER BY p.data_hora NULLS LAST, p.id
        """, (source, championship_id, season, team_id, team_id)).fetchall()
    report = analyze_team(matches, team_id, last=last, venue=venue, opponent_id=opponent_id)
    return {"time": team, "campeonato": championship, "origem": source,
            "coletas_utilizadas_na_base": sorted({m["coletado_em"].isoformat() for m in matches}), **report}
