"""Uma captura da temporada da Premier para agenda e placares atuais."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path

import httpx
from dotenv import dotenv_values


def collect_premier_season(season: int, *, transport: httpx.BaseTransport | None = None,
                           env_file: Path = Path('.env')) -> dict:
    if type(season) is not int or not 2000 <= season <= 2100:
        raise ValueError('Temporada inicial inválida.')
    values = {**dotenv_values(env_file, interpolate=False), **os.environ}
    token = (values.get('FOOTBALL_DATA_API_KEY') or '').strip()
    if not token or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError('Preencha FOOTBALL_DATA_API_KEY no .env.')
    with httpx.Client(timeout=30, follow_redirects=False, transport=transport,
                      headers={'X-Auth-Token': token, 'Accept': 'application/json'}) as client:
        try:
            response = client.get('https://api.football-data.org/v4/competitions/PL/matches',
                                  params={'season': season, 'limit': 500})
        except httpx.RequestError:
            raise ValueError('Falha de conexão com Football-data.org.') from None
    if response.status_code != 200:
        raise ValueError(f'Football-data.org: HTTP {response.status_code}; verifique plano e cota.')
    try:
        payload = json.loads(response.text.replace(token, '[REDACTED]'))
    except ValueError:
        raise ValueError('Football-data.org retornou JSON inválido.') from None
    games = payload.get('matches') if isinstance(payload, dict) else None
    count = payload.get('resultSet', {}).get('count') if isinstance(payload, dict) else None
    if (not isinstance(games, list) or type(count) is not int or count != len(games)
            or count > 500 or any(not isinstance(g, dict) or type(g.get('id')) is not int
                               or not isinstance(g.get('competition'), dict)
                               or g['competition'].get('code') != 'PL' for g in games)
            or len({g['id'] for g in games}) != len(games)):
        raise ValueError('Captura da Premier incompleta ou inconsistente.')
    return {'provedor': 'football-data', 'competicao': 'PL', 'temporada_inicio': season,
            'capturado_em': datetime.now(timezone.utc).isoformat(), 'jogos': games, 'total': count}
