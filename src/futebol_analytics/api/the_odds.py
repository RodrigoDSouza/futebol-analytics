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


def _integer_header(response: httpx.Response, name: str) -> int | None:
    try:
        return int(response.headers[name])
    except (KeyError, ValueError):
        return None
