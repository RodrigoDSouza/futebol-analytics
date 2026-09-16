"""Importa resultados da Premier via football-data.org para o banco configurado."""

from argparse import ArgumentParser
from pathlib import Path

from futebol_analytics.api.league import collect_premier_season
from futebol_analytics.config.settings import load_database_settings
from futebol_analytics.database.csv_store import import_premier_api
from futebol_analytics.database.store import SnapshotStore


parser = ArgumentParser()
parser.add_argument('--inicio', type=int, default=2025)
parser.add_argument('--env', type=Path, default=Path('.env'))
args = parser.parse_args()

capture = collect_premier_season(args.inicio, env_file=args.env)
season = f'{args.inicio}/{args.inicio + 1}'
result = import_premier_api(SnapshotStore(load_database_settings(args.env)), capture, season)
print(f"Premier {season}: {result['jogos']} jogos importados de football-data.org.")
