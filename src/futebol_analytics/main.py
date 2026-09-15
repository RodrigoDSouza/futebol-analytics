"""Interface de terminal da Fase 1."""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
from uuid import UUID

from futebol_analytics.api.client import DadosFutebolClient
from futebol_analytics.api.exceptions import DadosFutebolError
from futebol_analytics.config.settings import ConfigurationError, load_settings, load_database_settings
from futebol_analytics.database.store import DatabaseError, RESOURCES, SnapshotStore
from futebol_analytics.sync import synchronize
from futebol_analytics.database.normalized import process_local
from futebol_analytics.database.statistics import list_teams, team_report, DEFAULT_SOURCE
from futebol_analytics.database.forecast import upcoming, forecast
from futebol_analytics.api.football_csv import download, LEAGUES
from futebol_analytics.database.csv_store import import_csv, read_csv, read_csv_original
from futebol_analytics.api.betano import diagnose
from futebol_analytics.analysis.odds import evaluate
from futebol_analytics.api.current import collect, PROVIDERS
from futebol_analytics.standard import collect_standard
from zoneinfo import ZoneInfo
from futebol_analytics.database.league_rows import read_brasileirao_goals
from futebol_analytics.analysis.focus import evaluate_focus
from futebol_analytics.api.league import collect_premier_season
from futebol_analytics.database.league_rows import read_brasileirao_schedule
from futebol_analytics.analysis.tracker import track_focus
from futebol_analytics.analysis.backtest import backtest
from futebol_analytics.analysis.historical_odds import compare_historical_odds


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Futebol Analytics — consultas à API Dados Futebol")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validar-chave", help="Verifica a credencial no servidor sem exibi-la")
    sub = commands.add_parser("coletar-atuais", help="Captura jogos de uma data UTC em API internacional")
    sub.add_argument("--provedor", choices=list(PROVIDERS), required=True)
    sub.add_argument("--data", required=True, help="YYYY-MM-DD, dia UTC")
    sub.add_argument("--saida", type=Path, required=True)
    sub = commands.add_parser("coletar-padrao", help="Coleta agenda de seis competições em APIs permitidas")
    sub.add_argument("--data", default=datetime.now(ZoneInfo('America/Sao_Paulo')).date().isoformat(),
                     help="YYYY-MM-DD, dia em São Paulo")
    sub.add_argument("--saida", type=Path, required=True)
    sub = commands.add_parser("avaliar-foco", help="Avalia over 1,5, over 2,5 e ambos marcam nas duas ligas locais")
    sub.add_argument("--premier-temporada", default="2025/2026")
    sub.add_argument("--brasileirao-temporada", default="2026")
    sub.add_argument("--saida", type=Path, required=True)
    sub = commands.add_parser("avaliar-odds-premier", help="Compara previsões e odds históricas da Premier")
    sub.add_argument("--temporada", default="2025/2026")
    sub.add_argument("--saida", type=Path, required=True)
    sub = commands.add_parser("acompanhar-foco", help="Agenda e benchmarks de over 1,5, over 2,5 e ambos marcam")
    sub.add_argument("--premier-ano", type=int, default=datetime.now(ZoneInfo('America/Sao_Paulo')).year)
    sub.add_argument("--brasileirao-temporada", default=str(datetime.now(ZoneInfo('America/Sao_Paulo')).year))
    sub.add_argument("--saida", type=Path, required=True)
    sub = commands.add_parser("atualizar-ligas-csv", help="Importa as cinco ligas e registra cobertura e falhas")
    sub.add_argument("--temporada", required=True)
    sub.add_argument("--saida", type=Path, required=True)
    sub = commands.add_parser("diagnosticar-betano", help="Testa acesso público; ainda não extrai odds")
    sub.add_argument("--saida", type=Path, required=True)
    sub = commands.add_parser("analisar-odds-local", help="Simula comparação de cotações JSON com Poisson local")
    sub.add_argument("arquivo", type=Path)
    sub.add_argument("--saida", type=Path, required=True)
    for name in ("importar-premier-csv", "premier-local", "importar-liga-csv", "liga-local"):
        sub = commands.add_parser(name)
        sub.add_argument("--temporada", required=True, help="Exemplo: 2026/2027")
        sub.add_argument("--liga", choices=list(LEAGUES), default="E0")
    for command in ("campeonatos", "brasileirao", "partidas", "tabela"):
        sub = commands.add_parser(command)
        sub.add_argument("--temporada", default="2026")
        if command in ("partidas", "tabela"):
            sub.add_argument("--campeonato-id", type=int, help="Sem ID, localiza a Série A da temporada")
        if command in ("campeonatos", "partidas"):
            sub.add_argument("--pagina", type=int, default=1)
            sub.add_argument("--por-pagina", type=int, default=15)
        if command == "partidas":
            sub.add_argument("--rodada", type=int)
            sub.add_argument("--time-id", type=int)
            sub.add_argument("--status", choices=["aguardando", "ao_vivo", "encerrado", "adiado"])
            sub.add_argument("--data-inicio", help="YYYY-MM-DD")
            sub.add_argument("--data-fim", help="YYYY-MM-DD")
    stats = commands.add_parser("estatisticas", help="Consulta os campos disponíveis para uma partida")
    stats.add_argument("partida_id", type=int)
    commands.add_parser("banco-iniciar", help="Cria a tabela de capturas no PostgreSQL configurado")
    commands.add_parser("normalizar-local", help="Reconstrói tabelas derivadas usando somente capturas locais")
    commands.add_parser("auditar-local", help="Examina qualidade e cobertura das capturas sem acessar a API")
    for command in ("proximas-locais", "prever-partida"):
        sub = commands.add_parser(command)
        sub.add_argument("--campeonato-id", type=int, required=True)
        sub.add_argument("--temporada", default="2026")
        sub.add_argument("--origem", default=DEFAULT_SOURCE)
        if command == "prever-partida":
            sub.add_argument("partida_id", type=int)
    for command in ("times-local", "analisar-time"):
        sub = commands.add_parser(command)
        sub.add_argument("--campeonato-id", type=int, required=True)
        sub.add_argument("--temporada", default="2026")
        sub.add_argument("--origem", default=DEFAULT_SOURCE)
        if command == "analisar-time":
            sub.add_argument("time_id", type=int)
            sub.add_argument("--ultimos", type=int, choices=(5, 10))
            sub.add_argument("--mando", choices=("todos", "mandante", "visitante"), default="todos")
            sub.add_argument("--adversario-id", type=int)
    for command in ("sincronizar", "local", "historico"):
        sub = commands.add_parser(command)
        sub.add_argument("recurso", choices=RESOURCES)
        sub.add_argument("escopo", help="Temporada para campeonatos; ID do campeonato ou da partida nos demais")
        if command == "sincronizar":
            sub.add_argument("--max-paginas", type=int, default=100)
        elif command == "local":
            sub.add_argument("--captura-id", type=UUID, help="Sem ID, retorna a captura mais recente")
        else:
            sub.add_argument("--limite", type=int, default=20)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "acompanhar-foco":
            store = SnapshotStore(load_database_settings())
            brazil = read_brasileirao_goals(store, args.brasileirao_temporada)
            premier = collect_premier_season(args.premier_ano)
            now = datetime.now(timezone.utc)
            schedule = read_brasileirao_schedule(store, brazil['campeonato_id'],
                                                 args.brasileirao_temporada, now)
            result = track_focus(premier, brazil, schedule, now)
            args.saida.parent.mkdir(parents=True, exist_ok=True)
            args.saida.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f"Acompanhamento: {args.saida}; jogos: " + ', '.join(
                f"{name}={len(games)}" for name, games in result['agenda_7_dias'].items()))
            return 0
        if args.command == "avaliar-foco":
            store = SnapshotStore(load_database_settings())
            result = evaluate_focus(read_csv(store, args.premier_temporada, 'E0'),
                                    read_brasileirao_goals(store, args.brasileirao_temporada))
            args.saida.parent.mkdir(parents=True, exist_ok=True)
            args.saida.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
            print(f"Avaliação: {args.saida}; indicações: 0")
            return 0
        if args.command == "avaliar-odds-premier":
            store = SnapshotStore(load_database_settings())
            evaluation = backtest(read_csv(store, args.temporada, 'E0')['partidas'])
            result = compare_historical_odds(read_csv_original(store, args.temporada, 'E0'),
                                             evaluation['previsoes'])
            result['temporada'] = args.temporada
            args.saida.parent.mkdir(parents=True, exist_ok=True)
            args.saida.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f"Comparação histórica: {args.saida}; jogos: {result['jogos_avaliados']}; indicações: 0")
            return 0
        if args.command == "coletar-padrao":
            result = collect_standard(datetime.strptime(args.data, '%Y-%m-%d').date())
            args.saida.parent.mkdir(parents=True, exist_ok=True)
            args.saida.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            print(f"Relatório: {args.saida}; " + ', '.join(f"{k}={v['status']}:{v['jogos']}"
                  for k, v in result['resumo'].items()))
            return 0 if all(item['status'] == 'coletado' for item in result['competicoes'].values()) else 2
        if args.command == "coletar-atuais":
            result = collect(args.provedor, args.data)
            args.saida.parent.mkdir(parents=True, exist_ok=True)
            args.saida.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Captura: {args.saida}; jogos: {result['jogos']}")
            return 0
        if args.command == "atualizar-ligas-csv":
            store = SnapshotStore(load_database_settings())
            store.initialize()
            result = {"consultado_em": datetime.now(timezone.utc).isoformat(), "ligas": [], "erros": []}
            for league in LEAGUES:
                try:
                    result["ligas"].append(import_csv(store, download(args.temporada, league), args.temporada, league))
                except ValueError as error:
                    result["erros"].append({"liga": league, "motivo": str(error)})
                    if "429" in str(error):
                        break
            result["nao_processadas"] = [league for league in LEAGUES if league not in
                {r["liga"] for r in result["ligas"] + result["erros"]}]
            args.saida.parent.mkdir(parents=True, exist_ok=True)
            args.saida.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Ligas importadas: {len(result['ligas'])}; falhas: {len(result['erros'])}. Relatório: {args.saida}")
            return 1 if result["erros"] else 0
        if args.command in ("diagnosticar-betano", "analisar-odds-local"):
            if args.command == "diagnosticar-betano":
                result = diagnose()
            else:
                quotes = json.loads(args.arquivo.read_text(encoding="utf-8-sig"))
                store = SnapshotStore(load_database_settings())
                now = datetime.now(timezone.utc)
                result = evaluate(quotes, lambda mid, cid, season: forecast(store, mid, cid, season, now=now), now=now)
            args.saida.parent.mkdir(parents=True, exist_ok=True)
            args.saida.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            print(f"Relatório: {args.saida} — status: {result['status']}")
            # Diagnóstico não é coleta: falha explícita para qualquer agendador.
            return 2 if args.command == "diagnosticar-betano" else 0
        if args.command in ("importar-premier-csv", "premier-local", "importar-liga-csv", "liga-local"):
            store = SnapshotStore(load_database_settings())
            if args.command in ("importar-premier-csv", "importar-liga-csv"):
                store.initialize()
                result = import_csv(store, download(args.temporada, args.liga), args.temporada, args.liga)
            else:
                result = read_csv(store, args.temporada, args.liga)
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 0
        if args.command in ("proximas-locais", "prever-partida"):
            store = SnapshotStore(load_database_settings())
            if args.command == "proximas-locais":
                result = upcoming(store, args.campeonato_id, args.temporada, args.origem)
            else:
                result = forecast(store, args.partida_id, args.campeonato_id, args.temporada, args.origem)
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 0
        if args.command in ("times-local", "analisar-time"):
            store = SnapshotStore(load_database_settings())
            if args.command == "times-local":
                result = list_teams(store, args.campeonato_id, args.temporada, args.origem)
            else:
                result = team_report(store, args.time_id, args.campeonato_id, args.temporada,
                                     last=args.ultimos, venue=args.mando, opponent_id=args.adversario_id,
                                     source=args.origem)
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 0
        if args.command in ("normalizar-local", "auditar-local"):
            report = process_local(SnapshotStore(load_database_settings()), persist=args.command == "normalizar-local")
            print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
            return 0
        if args.command in ("banco-iniciar", "sincronizar", "local", "historico"):
            store = SnapshotStore(load_database_settings())
            if args.command == "banco-iniciar":
                store.initialize()
                print("Tabela de capturas pronta no PostgreSQL.")
            elif args.command == "sincronizar":
                settings = load_settings()
                # Falha antes de consumir API se o banco/tabela não estiver disponível.
                store.history(args.recurso, args.escopo, limit=1)
                with DadosFutebolClient(settings) as client:
                    capture_id = synchronize(client, store, args.recurso, args.escopo,
                                             settings.base_url, max_pages=args.max_paginas)
                print(f"Captura gravada: {capture_id}")
            else:
                scope = args.escopo
                if args.recurso != "campeonatos" and scope.isascii() and scope.isdigit():
                    scope = str(int(scope))
                if args.command == "local":
                    result = store.read(args.recurso, scope, snapshot_id=args.captura_id)
                else:
                    result = store.history(args.recurso, scope, limit=args.limite)
                print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
            return 0
        settings = load_settings()
        with DadosFutebolClient(settings) as client:
            if args.command == "validar-chave":
                client.validar_api_key()
                print("API Key validada pelo servidor.")
                return 0
            if args.command == "campeonatos":
                result = client.listar_campeonatos(temporada=args.temporada, pagina=args.pagina,
                                                  por_pagina=args.por_pagina)
            elif args.command == "brasileirao":
                result = client.localizar_brasileirao(args.temporada)
            elif args.command == "estatisticas":
                result = client.consultar_estatisticas(args.partida_id)
            else:
                championship_id = args.campeonato_id
                if championship_id is None:
                    championship_id = client.localizar_brasileirao(args.temporada)["id"]
                if args.command == "tabela":
                    result = client.consultar_tabela(championship_id)
                else:
                    result = client.listar_partidas(
                        championship_id, pagina=args.pagina, por_pagina=args.por_pagina,
                        rodada=args.rodada, status=args.status, time_id=args.time_id,
                        data_inicio=args.data_inicio, data_fim=args.data_fim,
                    )
            # Defesa adicional caso uma resposta inesperada reproduza a credencial.
            print(json.dumps(result, ensure_ascii=False, indent=2).replace(settings.api_key, "[REDACTED]"))
        return 0
    except OSError:
        print("Erro: não foi possível ler ou gravar o arquivo solicitado.", file=sys.stderr)
        return 1
    except (ConfigurationError, DadosFutebolError, DatabaseError, ValueError) as error:
        print(f"Erro: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
