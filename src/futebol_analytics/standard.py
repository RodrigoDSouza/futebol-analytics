"""Agenda diária das competições escolhidas, em fontes com API autorizada."""

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import unicodedata
from zoneinfo import ZoneInfo

from futebol_analytics.api.client import DadosFutebolClient
from futebol_analytics.api.current import collect
from futebol_analytics.api.exceptions import DadosFutebolError
from futebol_analytics.config.settings import load_settings


ZONE = ZoneInfo('America/Sao_Paulo')
FOOTBALL_DATA = {
    'brasileirao': 'BSA', 'premier_league': 'PL',
    'champions_league': 'CL', 'libertadores': 'CLI',
}


def _normalized(value: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', value.casefold())
                   if not unicodedata.combining(c)).strip()


def _copa_brasil(day: date) -> list[dict]:
    with DadosFutebolClient(load_settings()) as client:
        matches = []
        for page in range(1, 101):
            result = client.listar_campeonatos(temporada=str(day.year), pagina=page)
            matches += [r for r in result['data'] if _normalized(str(r.get('nome', ''))) == 'copa do brasil'
                        and str(r.get('temporada')) == str(day.year)]
            if page >= result['meta'].get('ultima_pagina', 1):
                break
        if len(matches) != 1 or type(matches[0].get('id')) is not int:
            raise ValueError('Copa do Brasil não localizada de forma única no plano disponível.')
        rows = []
        for page in range(1, 101):
            result = client.listar_partidas(matches[0]['id'], pagina=page, por_pagina=100,
                                             data_inicio=day.isoformat(), data_fim=day.isoformat())
            rows.extend(result['data'])
            if page >= result['meta'].get('ultima_pagina', 1):
                break
        return rows


def collect_standard(day: date, *, fetch=collect, copa_fetch=_copa_brasil) -> dict:
    if not isinstance(day, date):
        raise ValueError('Informe uma data válida.')
    report = {'data_sao_paulo': day.isoformat(), 'coletado_em': datetime.now(timezone.utc).isoformat(),
              'fonte_soccerstats': 'consulta_pontual_apenas; automação proibida pelos termos',
              'competicoes': {}}
    for name, code in FOOTBALL_DATA.items():
        captures, errors, games = [], [], {}
        for utc_day in (day, day + timedelta(days=1)):
            try:
                capture = fetch('football-data', utc_day.isoformat(), competitions=(code,))
                captures.append({'data_utc': utc_day.isoformat(), 'jogos_recebidos': capture['jogos']})
                for row in capture['partidas']:
                    if row.get('competition', {}).get('code') != code:
                        continue
                    kickoff = datetime.fromisoformat(row['utcDate'].replace('Z', '+00:00'))
                    if kickoff.tzinfo is None:
                        raise ValueError('Horário UTC sem fuso na resposta.')
                    if kickoff.astimezone(ZONE).date() == day:
                        games[row['id']] = row
            except (ValueError, KeyError, TypeError) as error:
                errors.append({'data_utc': utc_day.isoformat(), 'motivo': str(error)})
        report['competicoes'][name] = {'fonte': 'football-data.org', 'codigo': code,
            'status': 'erro' if errors else 'coletado', 'capturas': captures, 'erros': errors,
            'jogos': list(games.values()) if not errors else []}
    try:
        games = copa_fetch(day)
        report['competicoes']['copa_do_brasil'] = {'fonte': 'Dados Futebol', 'status': 'coletado',
                                                   'jogos': games, 'erros': []}
    except (DadosFutebolError, ValueError) as error:
        report['competicoes']['copa_do_brasil'] = {'fonte': 'Dados Futebol', 'status': 'erro',
                                                   'jogos': [], 'erros': [{'motivo': str(error)}]}
    report['competicoes']['sul_americana'] = {'fonte': None, 'status': 'sem_fonte_validada',
        'jogos': [], 'erros': [{'motivo': 'Plano e identificador de competição ainda não validados em API permitida.'}]}
    report['resumo'] = {name: {'status': item['status'], 'jogos': len(item['jogos'])}
                         for name, item in report['competicoes'].items()}
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description='Coleta diária padrão de seis competições')
    parser.add_argument('--data', default=datetime.now(ZONE).date().isoformat(), help='Dia em São Paulo, YYYY-MM-DD')
    parser.add_argument('--saida', type=Path, required=True)
    args = parser.parse_args()
    try:
        day = date.fromisoformat(args.data)
        report = collect_standard(day)
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"Relatório: {args.saida}; " + ', '.join(f"{k}={v['status']}:{v['jogos']}"
              for k, v in report['resumo'].items()))
        return 0 if all(item['status'] == 'coletado' for item in report['competicoes'].values()) else 2
    except (ValueError, OSError) as error:
        print(f'Falha na coleta padrão: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
