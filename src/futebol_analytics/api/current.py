"""Coletas por data em UTC; fontes independentes, sem inferir equivalências."""

from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values

PROVIDERS = {
    "football-data": ("FOOTBALL_DATA_API_KEY", "https://api.football-data.org/v4"),
    "sportmonks": ("SPORTMONKS_API_TOKEN", "https://api.sportmonks.com/v3/football"),
}


def collect(provider: str, day: str, *, transport: httpx.BaseTransport | None = None,
            env_file: Path = Path('.env'), competitions: tuple[str, ...] | None = None) -> dict[str, Any]:
    if provider not in PROVIDERS:
        raise ValueError("Provedor não suportado.")
    if date.fromisoformat(day).isoformat() != day:
        raise ValueError("Use data YYYY-MM-DD.")
    variable, base = PROVIDERS[provider]
    values = {**dotenv_values(env_file, interpolate=False), **os.environ}
    token = (values.get(variable) or '').strip()
    if not token or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError(f"Preencha {variable} no .env com a chave do próprio provedor.")
    start = datetime.now(timezone.utc).isoformat()
    headers = {"Accept": "application/json"}
    if provider == 'football-data':
        selected = competitions if competitions is not None else ('PL', 'PD', 'SA', 'BL1', 'FL1', 'BSA', 'CL')
        if not selected or any(not code.isascii() or not code.isalnum() or not code.isupper() for code in selected):
            raise ValueError('Códigos de competição inválidos.')
        headers['X-Auth-Token'] = token
        path = '/matches'
        params = {'date': day, 'competitions': ','.join(selected)}
        field = 'matches'
    else:
        path = '/fixtures/date/' + day
        params = {'api_token': token, 'timezone': 'UTC', 'filters': 'fixtureLeagues:501,271',
                  'include': 'participants;scores;state;statistics.type', 'per_page': 50}
        field = 'data'
    pages, rows, seen = [], [], set()
    with httpx.Client(timeout=30, follow_redirects=False, transport=transport, headers=headers) as client:
        for page in range(1, 11):
            if provider == 'sportmonks':
                params['page'] = page
            try:
                response = client.get(base + path, params=params)
            except httpx.RequestError:
                raise ValueError("Falha de conexão com o provedor; nenhuma captura parcial gravada.") from None
            if response.status_code != 200:
                raise ValueError(f"{provider}: HTTP {response.status_code}. Verifique chave, plano e cota; sem repetição automática.")
            try:
                # Metadados de paginação podem reproduzir token em URLs.
                payload = json.loads(response.text.replace(token, '[REDACTED]'))
            except ValueError:
                raise ValueError("Resposta não é JSON válido.") from None
            if not isinstance(payload, dict) or not isinstance(payload.get(field), list):
                raise ValueError("Resposta fora do formato documentado.")
            for row in payload[field]:
                if not isinstance(row, dict) or type(row.get('id')) is not int or row['id'] in seen:
                    raise ValueError("Partida inválida ou duplicada; captura rejeitada.")
                seen.add(row['id'])
                rows.append(row)
            pages.append(payload)
            if provider == 'football-data':
                break
            pagination = payload.get('pagination')
            if not isinstance(pagination, dict) or type(pagination.get('has_more')) is not bool:
                raise ValueError("Paginação ausente ou inválida; completude não confirmada.")
            if not pagination['has_more']:
                break
        else:
            raise ValueError("Limite de dez páginas atingido; captura incompleta rejeitada.")
    return {'origem': base, 'provedor': provider, 'data_utc': day, 'inicio_coleta': start,
            'competicoes_solicitadas': list(selected) if provider == 'football-data' else None,
            'fim_coleta': datetime.now(timezone.utc).isoformat(), 'jogos': len(rows),
            'jogos_com_estatisticas': sum(bool(r.get('statistics')) for r in rows),
            'partidas': rows, 'paginas': pages,
            'limitacoes': ['Data de consulta não comprova atualização ou cobertura completa do provedor.',
                          'Estatísticas ausentes não são zero. Dados ainda não ligados ao modelo ou aos CSVs.',
                          'Dia consultado em UTC; não equivale ao dia inteiro de São Paulo.']}
