"""Projeção relacional reconstruível a partir das capturas originais."""

from typing import Any

from futebol_analytics.database.store import SnapshotStore
from futebol_analytics.local_data import build_dataset


def process_local(store: SnapshotStore, *, persist: bool = False) -> dict[str, Any]:
    with store._connection() as connection:
        # A leitura e a publicação usam a mesma visão transacional das capturas.
        connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        if persist:
            connection.execute("SELECT pg_advisory_xact_lock(7062027)")
        captures = connection.execute("""
            SELECT * FROM futebol_capturas WHERE recurso IN ('campeonatos', 'rodadas')
            ORDER BY fim_coleta, gravado_em, id
        """).fetchall()
        dataset = build_dataset(captures)
        if persist:
            if not dataset.championships or not dataset.matches:
                raise ValueError("Não há dados suficientes para publicar. A projeção anterior foi preservada.")
            # Somente dados derivados são substituídos; futebol_capturas nunca é alterada.
            connection.execute("DELETE FROM futebol_partidas")
            connection.execute("DELETE FROM futebol_times")
            connection.execute("DELETE FROM futebol_campeonatos")
            with connection.cursor() as cursor:
                cursor.executemany("""
                    INSERT INTO futebol_campeonatos (origem, id, temporada, nome, tipo, captura_id)
                    VALUES (%(origem)s, %(id)s, %(temporada)s, %(nome)s, %(tipo)s, %(captura_id)s)
                """, dataset.championships)
                cursor.executemany("""
                    INSERT INTO futebol_times (origem, id, nome, sigla, captura_id)
                    VALUES (%(origem)s, %(id)s, %(nome)s, %(sigla)s, %(captura_id)s)
                """, dataset.teams)
                cursor.executemany("""
                    INSERT INTO futebol_partidas
                    (origem, campeonato_id, temporada, id, rodada, mandante_id, visitante_id,
                     status, data_hora, placar_mandante, placar_visitante, captura_id)
                    VALUES (%(origem)s, %(campeonato_id)s, %(temporada)s, %(id)s, %(rodada)s,
                            %(mandante_id)s, %(visitante_id)s, %(status)s, %(data_hora)s,
                            %(placar_mandante)s, %(placar_visitante)s, %(captura_id)s)
                """, dataset.matches)
        return dataset.report
