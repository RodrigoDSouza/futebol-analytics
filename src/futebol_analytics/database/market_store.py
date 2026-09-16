"""Persistência normalizada e retenção de odds e previsões."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from statistics import median
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from futebol_analytics.database.store import SnapshotStore
from futebol_analytics.analysis.opportunities import canonical_team
from futebol_analytics.analysis.calibration import calibration_report, grouped_calibration


def checkpoint(kickoff: datetime, captured: datetime) -> str | None:
    remaining = kickoff - captured
    if remaining <= timedelta(0):
        return None
    # Com três execuções diárias, esta é a última observação operacional antes do jogo.
    if remaining <= timedelta(hours=8):
        return "fechamento"
    if timedelta(hours=16) <= remaining <= timedelta(hours=32):
        return "24h"
    return "abertura"


def save_odds(store: SnapshotStore, capture: dict[str, Any]) -> dict[str, int]:
    captured = _time(capture["capturado_em"])
    provider, league = capture["provedor"], capture["liga"]
    details: list[dict[str, Any]] = []
    consensuses: list[dict[str, Any]] = []
    events = 0
    with store._connection() as connection:
        raw_id = uuid4()
        connection.execute("""
            INSERT INTO futebol_odds_capturas (id, provedor, capturado_em, expira_em, conteudo)
            VALUES (%s, %s, %s, %s, %s)
        """, (raw_id, provider, captured, captured + timedelta(days=7), Jsonb(capture)))
        for event in capture["eventos"]:
            event_id = str(event.get("id") or "").strip()
            home, away = event.get("home_team"), event.get("away_team")
            kickoff = _time(event.get("commence_time"))
            if not event_id or not isinstance(home, str) or not isinstance(away, str) or home == away:
                continue
            events += 1
            connection.execute("""
                INSERT INTO futebol_odds_eventos
                    (provedor, liga, evento_id, inicio, mandante, visitante, atualizado_em)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (provedor, liga, evento_id) DO UPDATE SET
                    inicio=EXCLUDED.inicio, mandante=EXCLUDED.mandante,
                    visitante=EXCLUDED.visitante, atualizado_em=EXCLUDED.atualizado_em
            """, (provider, league, event_id, kickoff, home, away, captured))
            rows = _details(event, provider, league, captured)
            details.extend(rows)
            mark = checkpoint(kickoff, captured)
            if mark:
                consensuses.extend(_consensus_rows(provider, league, event_id, mark, captured, rows))
        if details:
            connection.execute("""
                INSERT INTO futebol_odds_detalhes
                    (provedor, liga, evento_id, capturado_em, casa, mercado, selecao, linha, odd)
                SELECT provedor, liga, evento_id, capturado_em, casa, mercado, selecao, linha, odd
                FROM jsonb_to_recordset(%s::jsonb) AS row(
                    provedor text, liga text, evento_id text, capturado_em timestamptz,
                    casa text, mercado text, selecao text, linha numeric, odd numeric)
                ON CONFLICT DO NOTHING
            """, (Jsonb(_json_rows(details)),))
        if consensuses:
            connection.execute("""
                INSERT INTO futebol_odds_consensos
                    (provedor, liga, evento_id, checkpoint, mercado, selecao, linha,
                     observado_em, casas, odd_mediana, odd_melhor, probabilidade_justa)
                SELECT provedor, liga, evento_id, checkpoint, mercado, selecao, linha,
                       observado_em, casas, odd_mediana, odd_melhor, probabilidade_justa
                FROM jsonb_to_recordset(%s::jsonb) AS row(
                    provedor text, liga text, evento_id text, checkpoint text, mercado text,
                    selecao text, linha numeric, observado_em timestamptz, casas integer,
                    odd_mediana numeric, odd_melhor numeric, probabilidade_justa numeric)
                ON CONFLICT (provedor, liga, evento_id, checkpoint, mercado, selecao, linha)
                DO UPDATE SET
                    observado_em = CASE WHEN futebol_odds_consensos.checkpoint='abertura'
                        THEN futebol_odds_consensos.observado_em ELSE EXCLUDED.observado_em END,
                    casas = CASE WHEN futebol_odds_consensos.checkpoint='abertura'
                        THEN futebol_odds_consensos.casas ELSE EXCLUDED.casas END,
                    odd_mediana = CASE WHEN futebol_odds_consensos.checkpoint='abertura'
                        THEN futebol_odds_consensos.odd_mediana ELSE EXCLUDED.odd_mediana END,
                    odd_melhor = CASE WHEN futebol_odds_consensos.checkpoint='abertura'
                        THEN futebol_odds_consensos.odd_melhor ELSE EXCLUDED.odd_melhor END,
                    probabilidade_justa = CASE WHEN futebol_odds_consensos.checkpoint='abertura'
                        THEN futebol_odds_consensos.probabilidade_justa ELSE EXCLUDED.probabilidade_justa END
            """, (Jsonb(_json_rows(consensuses)),))
    return {"eventos": events, "odds_detalhadas": len(details)}


def cleanup(store: SnapshotStore, *, now: datetime | None = None,
            raw_days: int = 7, detail_days: int = 30) -> dict[str, int]:
    if raw_days < 1 or detail_days < raw_days:
        raise ValueError("Retenção inválida: detalhes devem durar ao menos tanto quanto o JSON bruto.")
    now = _time(now or datetime.now(timezone.utc))
    with store._connection() as connection:
        raw = connection.execute("""
            WITH removidas AS (DELETE FROM futebol_odds_capturas WHERE expira_em < %s RETURNING 1)
            SELECT count(*) AS total FROM removidas
        """, (now,)).fetchone()["total"]
        details = connection.execute("""
            WITH removidas AS (DELETE FROM futebol_odds_detalhes WHERE capturado_em < %s RETURNING 1)
            SELECT count(*) AS total FROM removidas
        """, (now - timedelta(days=detail_days),)).fetchone()["total"]
    return {"capturas_excluidas": raw, "odds_detalhadas_excluidas": details}


def storage_report(store: SnapshotStore, *, limit_bytes: int = 500_000_000) -> dict[str, Any]:
    with store._connection() as connection:
        rows = connection.execute("""
            SELECT c.relname AS tabela, pg_total_relation_size(c.oid) AS bytes
            FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
            WHERE n.nspname='public' AND c.relkind='r'
            ORDER BY bytes DESC
        """).fetchall()
        total = connection.execute(
            "SELECT pg_database_size(current_database()) AS bytes").fetchone()["bytes"]
    return {"total_bytes": total, "limite_referencia_bytes": limit_bytes,
            "percentual_limite": total / limit_bytes * 100,
            "tabelas": rows, "nivel": "critico" if total >= .9*limit_bytes else
            "atencao" if total >= .75*limit_bytes else "observacao" if total >= .6*limit_bytes else "normal"}


def upcoming_odds(store: SnapshotStore, league: str, *, now: datetime | None = None,
                  days: int = 14) -> list[dict[str, Any]]:
    """Retorna abertura e último consenso dos eventos futuros, sem consumir API."""
    if league not in ("premier_league", "brasileirao") or not 1 <= days <= 30:
        raise ValueError("Liga ou janela de próximos jogos inválida.")
    now = _time(now or datetime.now(timezone.utc))
    with store._connection() as connection:
        rows = connection.execute("""
            WITH recentes AS (
                SELECT DISTINCT ON
                    (provedor, liga, evento_id, mercado, selecao, linha)
                    provedor, liga, evento_id, checkpoint, mercado, selecao, linha,
                    observado_em, casas, odd_mediana, odd_melhor, probabilidade_justa
                FROM futebol_odds_consensos
                WHERE provedor='the-odds-api' AND liga=%s
                ORDER BY provedor, liga, evento_id, mercado, selecao, linha,
                         observado_em DESC, checkpoint DESC
            )
            SELECT e.evento_id, e.inicio, e.mandante, e.visitante,
                   r.checkpoint, r.mercado, r.selecao, r.linha,
                   r.observado_em, r.casas, r.odd_mediana, r.odd_melhor,
                   r.probabilidade_justa, a.odd_mediana AS odd_abertura
            FROM futebol_odds_eventos e
            JOIN recentes r ON (r.provedor, r.liga, r.evento_id) =
                               (e.provedor, e.liga, e.evento_id)
            LEFT JOIN futebol_odds_consensos a ON
                (a.provedor, a.liga, a.evento_id, a.mercado, a.selecao, a.linha, a.checkpoint) =
                (r.provedor, r.liga, r.evento_id, r.mercado, r.selecao, r.linha, 'abertura')
            WHERE e.provedor='the-odds-api' AND e.liga=%s
              AND e.inicio > %s AND e.inicio <= %s
            ORDER BY e.inicio, e.evento_id, r.mercado, r.linha, r.selecao
        """, (league, league, now, now + timedelta(days=days))).fetchall()
    numeric = ("linha", "odd_abertura", "odd_mediana", "odd_melhor", "probabilidade_justa")
    return [{**row, **{key: float(row[key]) if row.get(key) is not None else None for key in numeric}}
            for row in rows]


def save_predictions(store: SnapshotStore, league: str, report: dict[str, Any], *,
                     calculated_at: datetime | None = None) -> int:
    """Registra previsões pré-jogo de forma imutável por versão do modelo."""
    if league not in ("premier_league", "brasileirao"):
        raise ValueError("Liga inválida para registrar previsões.")
    calculated_at = _time(calculated_at or datetime.now(timezone.utc))
    model = str(report.get("modelo") or "").strip()
    if not model:
        raise ValueError("Relatório sem identificação do modelo.")
    rows = []
    specs = (("vitoria_mandante", "h2h", "mandante", 0),
             ("empate", "h2h", "empate", 0),
             ("vitoria_visitante", "h2h", "visitante", 0),
             ("over_1.5", "totals", "over", 1.5),
             ("over_2.5", "totals", "over", 2.5),
             ("ambas_marcam", "btts", "sim", 0))
    for game in report.get("resumo_jogos") or []:
        # A tabela referencia futebol_odds_eventos. Jogos vindos apenas da agenda
        # podem ser calculados e exibidos, mas ainda não possuem essa identidade.
        if not game.get("possui_evento_odds", True):
            continue
        if _time(game["inicio"]) <= calculated_at:
            continue
        evidence = {key: game.get(key) for key in ("mandante", "visitante", "inicio",
            "amostra_mandante", "amostra_visitante", "ultima_partida",
            "incerteza_aproximada", "confianca")}
        if isinstance(evidence.get("inicio"), datetime):
            evidence["inicio"] = evidence["inicio"].isoformat()
        for field, market, selection, line in specs:
            probability = game.get(field)
            if type(probability) not in (int, float) or not 0 < probability < 1:
                continue
            rows.append({"id": str(uuid4()), "provedor": "the-odds-api", "liga": league,
                "evento_id": str(game["evento_id"]), "calculado_em": calculated_at,
                "modelo": model, "versao": model.rsplit("_", 1)[-1], "mercado": market,
                "selecao": selection, "linha": line, "probabilidade": probability,
                "evidencia": evidence})
    if not rows:
        return 0
    with store._connection() as connection:
        connection.execute("""
            INSERT INTO futebol_previsoes
                (id, provedor, liga, evento_id, calculado_em, modelo, versao,
                 mercado, selecao, linha, probabilidade, evidencia)
            SELECT id::uuid, provedor, liga, evento_id, calculado_em, modelo, versao,
                   mercado, selecao, linha, probabilidade, evidencia
            FROM jsonb_to_recordset(%s::jsonb) AS row(
                id text, provedor text, liga text, evento_id text, calculado_em timestamptz,
                modelo text, versao text, mercado text, selecao text, linha numeric,
                probabilidade numeric, evidencia jsonb)
            ON CONFLICT (provedor, liga, evento_id, modelo, versao, mercado, selecao, linha)
            DO NOTHING
        """, (Jsonb(_json_rows(rows)),))
    return len(rows)


def evaluate_predictions(store: SnapshotStore, league: str, history: list[dict[str, Any]], *,
                         now: datetime | None = None) -> dict[str, Any]:
    """Avalia previsões registradas usando placares posteriormente disponíveis."""
    now = _time(now or datetime.now(timezone.utc))
    with store._connection() as connection:
        pending = connection.execute("""
            SELECT p.id, p.evento_id, p.mercado, p.selecao, p.linha, p.probabilidade,
                   e.inicio, e.mandante, e.visitante
            FROM futebol_previsoes p JOIN futebol_odds_eventos e USING (provedor, liga, evento_id)
            WHERE p.provedor='the-odds-api' AND p.liga=%s AND p.resultado IS NULL
              AND e.inicio < %s
        """, (league, now)).fetchall()
        updates = []
        for prediction in pending:
            utc_date = prediction["inicio"].astimezone(timezone.utc).date().isoformat()
            local_date = prediction["inicio"].astimezone(ZoneInfo("America/Sao_Paulo")).date().isoformat()
            matches = [row for row in history if str(row["data"]) in (utc_date, local_date)
                       and canonical_team(str(row["mandante"])) == canonical_team(prediction["mandante"])
                       and canonical_team(str(row["visitante"])) == canonical_team(prediction["visitante"])]
            if len(matches) != 1:
                continue
            match = matches[0]
            home, away = match["gols_mandante"], match["gols_visitante"]
            if prediction["mercado"] == "h2h":
                result = {"mandante": home > away, "empate": home == away,
                          "visitante": home < away}[prediction["selecao"]]
            elif prediction["mercado"] == "totals":
                result = home + away > float(prediction["linha"])
            elif prediction["mercado"] == "btts":
                result = home > 0 and away > 0
            else:
                continue
            updates.append((int(result), now, prediction["id"]))
        if updates:
            with connection.cursor() as cursor:
                cursor.executemany("""UPDATE futebol_previsoes SET resultado=%s, avaliado_em=%s
                    WHERE id=%s AND resultado IS NULL""", updates)
        performance = connection.execute("""
            SELECT mercado, selecao, linha, count(*) AS previsoes,
                   count(resultado) AS avaliadas,
                   avg(power(probabilidade-resultado, 2)) FILTER (WHERE resultado IS NOT NULL) AS brier
            FROM futebol_previsoes WHERE provedor='the-odds-api' AND liga=%s
            GROUP BY mercado, selecao, linha ORDER BY mercado, linha, selecao
        """, (league,)).fetchall()
        evaluated = connection.execute("""
            SELECT mercado, selecao, linha, probabilidade, resultado
            FROM futebol_previsoes
            WHERE provedor='the-odds-api' AND liga=%s AND resultado IS NOT NULL
            ORDER BY calculado_em, evento_id, mercado, selecao, linha
        """, (league,)).fetchall()
    evaluated = [{**row, "linha": float(row["linha"]),
                  "probabilidade": float(row["probabilidade"]),
                  "resultado": int(row["resultado"])} for row in evaluated]
    return {"avaliadas_agora": len(updates), "calibracao_geral": calibration_report(evaluated),
            "calibracao_por_mercado": grouped_calibration(evaluated), "desempenho": [
        {**row, "linha": float(row["linha"]),
         "brier": float(row["brier"]) if row["brier"] is not None else None}
        for row in performance]}


def _details(event: dict[str, Any], provider: str, league: str,
             captured: datetime) -> list[dict[str, Any]]:
    rows = []
    for bookmaker in event.get("bookmakers") or []:
        house = bookmaker.get("key") or bookmaker.get("title")
        if not isinstance(house, str) or not house:
            continue
        for market in bookmaker.get("markets") or []:
            market_key = market.get("key")
            if market_key not in ("h2h", "totals", "btts", "alternate_totals"):
                continue
            for outcome in market.get("outcomes") or []:
                price, selection = outcome.get("price"), outcome.get("name")
                if type(price) not in (int, float) or price <= 1 or not isinstance(selection, str):
                    continue
                point = outcome.get("point")
                rows.append({"provedor": provider, "liga": league,
                    "evento_id": str(event["id"]), "capturado_em": captured, "casa": house,
                    "mercado": market_key, "selecao": selection,
                    "linha": Decimal(str(point)) if type(point) in (int, float) else Decimal(0),
                    "odd": Decimal(str(price))})
    return rows


def _consensus_rows(provider: str, league: str, event_id: str,
                    mark: str, captured: datetime, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple, list[Decimal]] = defaultdict(list)
    for row in rows:
        grouped[(row["mercado"], row["selecao"], row["linha"])].append(row["odd"])
    medians = {key: Decimal(str(median(prices))) for key, prices in grouped.items()}
    margins: dict[tuple, Decimal] = defaultdict(Decimal)
    for (market, _selection, line), price in medians.items():
        margins[(market, line)] += Decimal(1) / price
    result = []
    for (market, selection, line), prices in grouped.items():
        # Linhas alternativas podem vir com apenas um lado em parte das casas.
        # Sem pelo menos duas seleções não existe margem removível nem consenso justo.
        selections = {key[1] for key in grouped if key[0] == market and key[2] == line}
        if len(selections) < 2:
            continue
        med = medians[(market, selection, line)]
        probability = (Decimal(1) / med) / margins[(market, line)]
        if not Decimal(0) < probability < Decimal(1):
            continue
        result.append({"provedor": provider, "liga": league, "evento_id": event_id,
            "checkpoint": mark, "mercado": market, "selecao": selection, "linha": line,
            "observado_em": captured, "casas": len(prices), "odd_mediana": med,
            "odd_melhor": max(prices), "probabilidade_justa": probability})
    return result


def _json_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: value.isoformat() if isinstance(value, datetime) else
             str(value) if isinstance(value, Decimal) else value for key, value in row.items()}
            for row in rows]


def _time(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Horário ausente ou sem fuso.")
    return value.astimezone(timezone.utc)
