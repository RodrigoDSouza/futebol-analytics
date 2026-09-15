"""Agenda -> cobertura local -> mercados -> fila de consulta de odds."""

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from futebol_analytics.api.current import collect
from futebol_analytics.analysis.multimarket import estimate
from futebol_analytics.config.settings import load_database_settings
from futebol_analytics.database.csv_store import read_csv
from futebol_analytics.database.store import SnapshotStore, DatabaseError
from futebol_analytics.journal import save_plan_record

LEAGUES = {'PL': 'E0', 'PD': 'SP1', 'SA': 'I1', 'BL1': 'D1', 'FL1': 'F1'}


def plan(captures: list[dict], day: date, now: datetime, load_history, mappings: dict) -> dict:
    zone = ZoneInfo('America/Sao_Paulo')
    if now.tzinfo is None:
        raise ValueError('Horário de execução exige fuso.')
    if day != now.astimezone(zone).date():
        raise ValueError('Planejamento operacional exige o dia atual; não é um backtest.')
    games, seen = [], set()
    for capture in captures:
        if capture.get('provedor') != 'football-data':
            raise ValueError('Agenda deve ser do Football-data.org.')
        observed = datetime.fromisoformat(capture['fim_coleta'])
        if observed.tzinfo is None or not timedelta(0) <= now-observed <= timedelta(hours=1):
            raise ValueError('Agenda antiga ou com horário inválido; atualize a API.')
        for fixture in capture['partidas']:
            if fixture['id'] in seen:
                continue
            seen.add(fixture['id'])
            kickoff = datetime.fromisoformat(fixture['utcDate'].replace('Z', '+00:00'))
            if kickoff.astimezone(zone).date() != day:
                continue
            game = {'id_api': fixture['id'], 'inicio': kickoff.isoformat(),
                    'mandante': fixture['homeTeam']['name'], 'visitante': fixture['awayTeam']['name'],
                    'status': 'nao_elegivel', 'motivo': None}
            games.append(game)
            if kickoff <= now or fixture.get('status') not in ('TIMED', 'SCHEDULED'):
                game['motivo'] = 'Jogo iniciado ou status da fonte incompatível.'
                continue
            league = LEAGUES.get(fixture['competition']['code'])
            if not league:
                game['motivo'] = 'Campeonato sem histórico CSV integrado neste fluxo.'
                continue
            season = f'{kickoff.year}/{kickoff.year+1}' if kickoff.month >= 7 else f'{kickoff.year-1}/{kickoff.year}'
            try:
                history = load_history(season, league)
            except ValueError as error:
                game['motivo'] = str(error)
                continue
            teams = {r[s] for r in history['partidas'] for s in ('mandante', 'visitante')}
            labels = []
            for side in ('homeTeam', 'awayTeam'):
                team = fixture[side]
                explicit = mappings.get(f'{league}:{team["id"]}')
                choices = {explicit} if explicit else {team.get('name'), team.get('shortName')}
                matches = choices & teams
                labels.append(next(iter(matches)) if len(matches) == 1 else None)
            if None in labels or labels[0] == labels[1]:
                game['motivo'] = 'Identidade de equipe não conciliada; cadastre ID da API e nome CSV no mapa.'
                continue
            analysis = estimate(history['partidas'], *labels, cutoff=day)
            game.update(analise=analysis, arquivo_id=str(history['arquivo']['id']),
                        ultima_data_resultados=history['resumo']['ultima_data'])
            age = (day-date.fromisoformat(history['resumo']['ultima_data'])).days
            if age < 0 or age > 3:
                game['motivo'] = 'Histórico fora do limite operacional de três dias.'
                continue
            markets = [m for m in analysis['mercados'] if m['status']=='experimental' and not m['mercado'].startswith('amarelos_')]
            if not markets:
                game['motivo'] = 'Amostra insuficiente nos mercados comparáveis.'
                continue
            game.update(status='aguardando_odds', mercados_prioritarios=sorted(markets, key=lambda m: -m['probabilidade_estimada']))
    queue = sorted([g for g in games if g['status']=='aguardando_odds'],
                   key=lambda g: (-g['mercados_prioritarios'][0]['probabilidade_estimada'], g['id_api']))[:3]
    return {'data': day.isoformat(), 'calculado_em': now.isoformat(), 'fuso': str(zone), 'jogos': games,
            'fila_betano': [g['id_api'] for g in queue], 'indicacoes': [],
            'status': 'aguardando_odds' if queue else 'sem_jogos_elegiveis',
            'limitacoes': ['Fila por probabilidade estimada, não por valor esperado. Não recomenda aposta antes da cotação.',
                          'Cartões amarelos não são automaticamente equivalentes ao mercado da Betano.',
                          'Leitura automática dos mercados da Betano ainda não validada; links exigem associação explícita.',
                          'Fluxo atual usa agenda Football-data e histórico CSV; outras fontes continuam separadas.']}


def main() -> int:
    parser = argparse.ArgumentParser(description='Planejamento diário experimental, sem executar apostas')
    parser.add_argument('--data', required=True)
    parser.add_argument('--saida', type=Path, required=True)
    parser.add_argument('--mapa', type=Path)
    parser.add_argument('--agenda', type=Path, nargs='+', help='Capturas existentes; sem essa opção consulta API')
    parser.add_argument('--registro-dir', type=Path, default=Path('reports/registros_diarios'),
                        help='Pasta de registros datados; cada execução cria um pacote novo')
    args = parser.parse_args()
    try:
        day = date.fromisoformat(args.data)
        captures = [json.loads(p.read_text(encoding='utf-8')) for p in args.agenda] if args.agenda else [
            collect('football-data', (day+timedelta(days=i)).isoformat()) for i in range(2)]
        # Dois dias UTC cobrem o dia civil inteiro em São Paulo.
        if not args.agenda:
            folder = Path('reports/agendas')
            folder.mkdir(parents=True, exist_ok=True)
            for capture in captures:
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
                (folder/f'{stamp}.json').write_text(json.dumps(capture, ensure_ascii=False, indent=2), encoding='utf-8')
        mapping = json.loads(args.mapa.read_text(encoding='utf-8')) if args.mapa else {}
        store = SnapshotStore(load_database_settings())
        histories = {}
        def load_history(season, league):
            key = f'{league}:{season}'
            if key not in histories:
                histories[key] = read_csv(store, season, league)
            return histories[key]
        report = plan(captures, day, datetime.now(timezone.utc), load_history, mapping)
        record = save_plan_record(args.registro_dir, captures, histories, mapping, report)
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"Relatório: {args.saida}; registro: {record}; status: {report['status']}; fila: {len(report['fila_betano'])}")
        return 0
    except (ValueError, OSError, DatabaseError) as error:
        print(f'Não foi possível planejar: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
