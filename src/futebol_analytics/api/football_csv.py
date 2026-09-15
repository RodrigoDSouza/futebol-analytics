"""CSV público da Premier League; sem autenticação ou chamadas à API brasileira."""

import csv
from datetime import datetime
import io
import re
from typing import Any

import httpx

LEAGUES = {"E0": "Premier League", "SP1": "La Liga", "I1": "Serie A", "D1": "Bundesliga", "F1": "Ligue 1"}

FIELDS = {
    "FTHG": "gols_mandante", "FTAG": "gols_visitante",
    "HC": "escanteios_mandante", "AC": "escanteios_visitante",
    "HY": "amarelos_mandante", "AY": "amarelos_visitante",
    "HR": "vermelhos_mandante", "AR": "vermelhos_visitante",
    "HS": "finalizacoes_mandante", "AS": "finalizacoes_visitante",
    "HST": "finalizacoes_alvo_mandante", "AST": "finalizacoes_alvo_visitante",
}


def source_url(season: str, league: str = "E0") -> str:
    if not re.fullmatch(r"20\d{2}/20\d{2}", season) or int(season[5:]) != int(season[:4]) + 1:
        raise ValueError("Use uma temporada como 2026/2027.")
    if league not in LEAGUES:
        raise ValueError("Liga n?o suportada.")
    code = season[2:4] + season[7:9]
    return f"https://football-data.co.uk/mmz4281/{code}/{league}.csv"


def download(season: str, league: str = "E0") -> str:
    try:
        response = httpx.get(source_url(season, league), timeout=30, follow_redirects=True)
    except httpx.RequestError:
        raise ValueError("Não foi possível baixar o CSV público.") from None
    if response.status_code != 200:
        raise ValueError(f"CSV indisponível: HTTP {response.status_code}. Não há repetição automática.")
    try:
        return response.content.decode("utf-8-sig")
    except UnicodeError:
        raise ValueError("Codificação do CSV não reconhecida.") from None


def parse_csv(content: str, season: str, league: str = "E0") -> list[dict[str, Any]]:
    source_url(season, league)
    reader = csv.DictReader(io.StringIO(content.lstrip('\ufeff')))
    required = {"Div", "Date", "HomeTeam", "AwayTeam", *FIELDS}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError("CSV sem os campos esperados de resultados, escanteios e cartões.")
    rows, keys = [], set()
    for number, row in enumerate(reader, 2):
        if not any(row.values()):
            continue
        if None in row or any(value is None for value in row.values()):
            raise ValueError(f"Linha {number}: número de colunas inconsistente.")
        home, away = row["HomeTeam"].strip(), row["AwayTeam"].strip()
        if row["Div"] != league or not home or not away or home == away:
            raise ValueError(f"Linha {number}: divisão ou times inválidos.")
        try:
            date = datetime.strptime(row["Date"], "%d/%m/%Y").date()
        except ValueError:
            raise ValueError(f"Linha {number}: data inválida.") from None
        if date.year not in (int(season[:4]), int(season[5:])):
            raise ValueError(f"Linha {number}: data fora dos anos da temporada.")
        key = (date, home, away)
        if key in keys:
            raise ValueError(f"Linha {number}: partida duplicada; arquivo não importado.")
        keys.add(key)
        record: dict[str, Any] = {"data": date.isoformat(), "mandante": home, "visitante": away}
        for field, name in FIELDS.items():
            value = row[field].strip()
            if value and not re.fullmatch(r"\d+", value):
                raise ValueError(f"Linha {number}: estatística {field} inválida.")
            record[name] = int(value) if value else None
        rows.append(record)
    if not rows:
        raise ValueError("CSV vazio; nenhuma importação gravada.")
    return rows
