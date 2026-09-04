"""Interface de linha de comando do Futebol Analytics."""

import argparse
import json
from typing import Any

from futebol_analytics.analysis.team_form import (
    SemPartidasEncerradasError,
    analisar_forma_time,
)
from futebol_analytics.api.client import DadosFutebolClient
from futebol_analytics.api.exceptions import DadosFutebolError
from futebol_analytics.config.settings import ConfigurationError, Settings
from futebol_analytics.services.campeonatos import (
    CampeonatoNaoEncontradoError,
    localizar_brasileirao_serie_a,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="futebol-analytics",
        description="Consulta dados da API Dados Futebol.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("perfil", help="Valida a API Key e mostra seu perfil.")

    championships = subcommands.add_parser(
        "campeonatos", help="Lista os campeonatos disponíveis."
    )
    championships.add_argument("--temporada", help="Ano com quatro dígitos.")
    championships.add_argument(
        "--status", choices=("em_andamento", "encerrado")
    )
    championships.add_argument(
        "--tipo", choices=("pontos-corridos", "mata-mata")
    )

    brasileirao = subcommands.add_parser(
        "brasileirao", help="Localiza o Brasileirão Série A."
    )
    brasileirao.add_argument("--temporada", default="2026")

    rounds = subcommands.add_parser(
        "rodadas", help="Consulta as rodadas e partidas de um campeonato."
    )
    rounds.add_argument("--campeonato-id", type=int, required=True)
    rounds.add_argument(
        "--numero",
        type=int,
        help="Exibe somente esta rodada; o filtro é aplicado localmente.",
    )

    standings = subcommands.add_parser(
        "tabela", help="Consulta a tabela de classificação de um campeonato."
    )
    standings.add_argument("--campeonato-id", type=int, required=True)

    analysis = subcommands.add_parser(
        "analisar-time", help="Analisa a forma recente de um time."
    )
    analysis.add_argument("--campeonato-id", type=int, required=True)
    analysis.add_argument("--time-id", type=int, required=True)
    analysis.add_argument("--jogos", type=int, choices=(5, 10), default=5)
    analysis.add_argument(
        "--mando",
        choices=("todos", "mandante", "visitante"),
        default="todos",
    )

    return parser


def execute(args: argparse.Namespace, client: DadosFutebolClient) -> Any:
    if args.command == "perfil":
        return client.consultar_perfil()
    if args.command == "campeonatos":
        return client.listar_campeonatos(
            temporada=args.temporada,
            status=args.status,
            tipo=args.tipo,
        )
    if args.command == "brasileirao":
        return localizar_brasileirao_serie_a(
            client,
            temporada=args.temporada,
        )
    if args.command == "rodadas":
        rounds = client.consultar_rodadas(args.campeonato_id)
        if args.numero is None:
            return rounds
        return [round_ for round_ in rounds if round_.get("numero") == args.numero]
    if args.command == "tabela":
        return client.consultar_tabela(args.campeonato_id)
    if args.command == "analisar-time":
        rounds = client.consultar_rodadas(args.campeonato_id)
        return analisar_forma_time(
            rounds,
            time_id=args.time_id,
            quantidade=args.jogos,
            mando=args.mando,
        )
    raise ValueError(f"Comando desconhecido: {args.command}")


def main() -> int:
    args = build_parser().parse_args()

    try:
        settings = Settings.from_env()
        with DadosFutebolClient(settings) as client:
            result = execute(args, client)
    except (
        ConfigurationError,
        DadosFutebolError,
        CampeonatoNaoEncontradoError,
        SemPartidasEncerradasError,
        ValueError,
    ) as exc:
        print(f"Erro: {exc}")
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
