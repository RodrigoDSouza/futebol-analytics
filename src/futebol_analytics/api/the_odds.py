"""Cliente mínimo da The Odds API para odds pré-jogo de futebol."""

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values


SPORTS = {
    "premier_league": "soccer_epl",
    "brasileirao": "soccer_brazil_campeonato",
}
# BTTS é um mercado adicional da API e exige uma chamada por evento. Mantemos o
# coletor automático nos mercados agregados para caber nos 500 créditos/mês.
MARKETS = ("h2h", "totals")
TARGET_MARKETS = ("btts", "alternate_totals")


def collect_odds(league: str, *, transport: httpx.BaseTransport | None = None,
                 env_file: Path = Path(".env")) -> dict[str, Any]:
    if league not in SPORTS:
        raise ValueError("Liga não suportada pela coleta de odds.")
    values = {**dotenv_values(env_file, interpolate=False), **os.environ}
    token = (values.get("THE_ODDS_API_KEY") or "").strip()
    if not token or not token.isascii() or any(char.isspace() for char in token):
        raise ValueError("Preencha THE_ODDS_API_KEY com a chave da The Odds API.")
    captured = datetime.now(timezone.utc)
    params = {
        # Uma região x dois mercados = dois créditos por liga/coleta.
        "apiKey": token, "regions": "eu", "markets": ",".join(MARKETS),
        "oddsFormat": "decimal", "dateFormat": "iso",
    }
    url = f"https://api.the-odds-api.com/v4/sports/{SPORTS[league]}/odds"
    try:
        with httpx.Client(timeout=30, follow_redirects=False, transport=transport) as client:
            response = client.get(url, params=params, headers={"Accept": "application/json"})
    except httpx.RequestError:
        raise ValueError("Falha de conexão com a The Odds API.") from None
    if response.status_code != 200:
        raise ValueError(f"The Odds API: HTTP {response.status_code}. Verifique chave, mercados e cota.")
    try:
        payload = response.json()
    except ValueError:
        raise ValueError("The Odds API retornou JSON inválido.") from None
    if not isinstance(payload, list) or any(not isinstance(event, dict) for event in payload):
        raise ValueError("The Odds API retornou formato inesperado.")
    return {
        "provedor": "the-odds-api", "liga": league, "capturado_em": captured.isoformat(),
        "creditos_restantes": _integer_header(response, "x-requests-remaining"),
        "creditos_usados": _integer_header(response, "x-requests-used"),
        "eventos": payload,
        "mercados": list(MARKETS),
        "limitacoes": [
            "Ambas marcam exige consulta individual por evento e não entra na coleta gratuita automática.",
            "Odds históricas anteriores à primeira coleta não estão disponíveis no plano gratuito.",
        ],
    }


def collect_event_odds(league: str, event_ids: list[str], *,
                       transport: httpx.BaseTransport | None = None,
                       env_file: Path = Path(".env"), max_events: int = 3) -> dict[str, Any]:
    """Consulta mercados extras somente para uma pré-seleção pequena e explícita."""
    if league not in SPORTS:
        raise ValueError("Liga não suportada pela coleta de odds.")
    unique = list(dict.fromkeys(str(value).strip() for value in event_ids if str(value).strip()))
    if not unique or len(unique) > max_events:
        raise ValueError(f"Selecione entre 1 e {max_events} eventos para a consulta direcionada.")
    values = {**dotenv_values(env_file, interpolate=False), **os.environ}
    token = (values.get("THE_ODDS_API_KEY") or "").strip()
    if not token or not token.isascii() or any(char.isspace() for char in token):
        raise ValueError("Preencha THE_ODDS_API_KEY com a chave da The Odds API.")
    captured = datetime.now(timezone.utc)
    merged: dict[str, dict[str, Any]] = {}
    failures: list[dict[str, Any]] = []
    remaining, used = None, None
    try:
        with httpx.Client(timeout=30, follow_redirects=False, transport=transport) as client:
            for event_id in unique:
                for market in TARGET_MARKETS:
                    url = (f"https://api.the-odds-api.com/v4/sports/{SPORTS[league]}"
                           f"/events/{event_id}/odds")
                    response = client.get(url, params={"apiKey": token, "regions": "eu",
                        "markets": market, "oddsFormat": "decimal", "dateFormat": "iso"},
                        headers={"Accept": "application/json"})
                    remaining = _integer_header(response, "x-requests-remaining") or remaining
                    used = _integer_header(response, "x-requests-used") or used
                    if response.status_code != 200:
                        failures.append({"evento_id": event_id, "mercado": market,
                                         "http": response.status_code,
                                         "motivo": _safe_api_message(response)})
                        continue
                    payload = response.json()
                    if not isinstance(payload, dict):
                        failures.append({"evento_id": event_id, "mercado": market,
                                         "http": 200, "motivo": "formato inesperado"})
                        continue
                    if event_id not in merged:
                        merged[event_id] = {**payload, "bookmakers": []}
                    _merge_bookmakers(merged[event_id]["bookmakers"], payload.get("bookmakers") or [])
    except httpx.RequestError:
        raise ValueError("Falha de conexão com a The Odds API.") from None
    except ValueError as error:
        if str(error).startswith("The Odds API"):
            raise
        raise ValueError("The Odds API retornou JSON inválido.") from None
    if not merged:
        summary = "; ".join(sorted({f"{item['mercado']}: HTTP {item['http']} · {item['motivo']}"
                                    for item in failures}))
        raise ValueError(f"Nenhum mercado adicional foi disponibilizado. {summary}")
    return {"provedor": "the-odds-api", "liga": league,
            "capturado_em": captured.isoformat(), "creditos_restantes": remaining,
            "creditos_usados": used, "eventos": list(merged.values()),
            "mercados": list(TARGET_MARKETS), "falhas": failures,
            "limitacoes": ["Consulta direcionada; o custo depende dos eventos e mercados solicitados."]}


def _safe_api_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return "resposta sem detalhe"
    if not isinstance(payload, dict):
        return "resposta sem detalhe"
    code = str(payload.get("error_code") or "").strip()
    message = str(payload.get("message") or "").strip()
    safe = " · ".join(value for value in (code, message) if value)
    # A API não deveria ecoar a chave, mas nunca repassamos parâmetros/URLs.
    return safe[:300] or "resposta sem detalhe"


def _merge_bookmakers(target: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> None:
    by_key = {str(item.get("key") or item.get("title")): item for item in target}
    for bookmaker in incoming:
        key = str(bookmaker.get("key") or bookmaker.get("title"))
        if key not in by_key:
            copy = {**bookmaker, "markets": list(bookmaker.get("markets") or [])}
            target.append(copy)
            by_key[key] = copy
        else:
            by_key[key].setdefault("markets", []).extend(bookmaker.get("markets") or [])


def _integer_header(response: httpx.Response, name: str) -> int | None:
    try:
        return int(response.headers[name])
    except (KeyError, ValueError):
        return None
