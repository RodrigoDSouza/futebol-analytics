"""Central local: consultas explícitas, histórico e modelos compartilhados."""

from datetime import datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

from futebol_analytics.api.current import collect
from futebol_analytics.api.football_csv import LEAGUES
from futebol_analytics.analysis.backtest import backtest
from futebol_analytics.analysis.focus import evaluate_focus
from futebol_analytics.analysis.tracker import track_focus
from futebol_analytics.analysis.opportunities import rank_opportunities, risk_plan
from futebol_analytics.api.league import collect_premier_season
from futebol_analytics.analysis.multimarket import estimate
from futebol_analytics.config.settings import load_database_settings
from futebol_analytics.database.store import SnapshotStore, DatabaseError
from futebol_analytics.database.csv_store import read_csv
from futebol_analytics.database.forecast import upcoming, forecast
from futebol_analytics.database.league_rows import read_brasileirao_goals, read_brasileirao_schedule
from futebol_analytics.daily import plan
from futebol_analytics.api.the_odds import collect_event_odds, collect_odds
from futebol_analytics.database.market_store import (evaluate_predictions, save_odds,
    model_decision_performance, save_model_decisions, save_predictions,
    storage_report, upcoming_odds)


COVERAGE_LABELS = {
    'gols_mandante': 'Gols do mandante', 'gols_visitante': 'Gols do visitante',
    'escanteios_mandante': 'Escanteios do mandante', 'escanteios_visitante': 'Escanteios do visitante',
    'amarelos_mandante': 'Cartões amarelos do mandante', 'amarelos_visitante': 'Cartões amarelos do visitante',
    'vermelhos_mandante': 'Cartões vermelhos do mandante', 'vermelhos_visitante': 'Cartões vermelhos do visitante',
    'finalizacoes_mandante': 'Finalizações do mandante', 'finalizacoes_visitante': 'Finalizações do visitante',
    'finalizacoes_alvo_mandante': 'Finalizações no alvo do mandante',
    'finalizacoes_alvo_visitante': 'Finalizações no alvo do visitante',
}

st.caption('Acompanhe Premier League e Brasileirão, consulte a agenda e avalie modelos com dados locais.')
decision_tab, focus_tab, data_tab, database_tab = st.tabs([
    'Hoje', 'Desempenho', 'Dados e modelos', 'Sistema'])
agenda_tab = csv_tab = poisson_tab = data_tab


def store():
    return SnapshotStore(load_database_settings())


def decision_inputs(db, league, today, market_rows):
    """Monta histórico e agenda sem tornar as odds obrigatórias para o modelo."""
    if league == 'brasileirao':
        brazil = read_brasileirao_goals(db, str(today.year))
        fixtures = read_brasileirao_schedule(
            db, brazil['campeonato_id'], str(today.year), datetime.now(ZoneInfo('UTC')), days=14)
        return brazil['partidas'], [dict(game, origem_agenda='dados-futebol') for game in fixtures]

    histories = []
    for selected_season in ('2025/2026', '2026/2027'):
        try:
            histories.extend(read_csv(db, selected_season, 'E0')['partidas'])
        except ValueError:
            pass
    if not histories:
        raise ValueError('Histórico da Premier indisponível.')
    tracking = st.session_state.get('acompanhamento_foco') or {}
    fixtures = []
    for game in tracking.get('agenda_7_dias', {}).get('premier_league', []):
        fixtures.append({'id': game.get('id') or f"pl:{game.get('inicio')}:{game.get('mandante')}",
                         'inicio': game.get('inicio'), 'mandante': game.get('mandante'),
                         'visitante': game.get('visitante'), 'origem_agenda': 'football-data'})
    return histories, fixtures


def calculate_decision(db, league, today, market_rows):
    histories, fixtures = decision_inputs(db, league, today, market_rows)
    db.initialize()
    performance = evaluate_predictions(db, league, histories)
    result = rank_opportunities(histories, market_rows, today=today, fixtures=fixtures)
    result['previsoes_registradas'] = save_predictions(db, league, result)
    result['decisoes_registradas'] = save_model_decisions(db, league, result)
    result['desempenho_estrategia'] = model_decision_performance(db, league)
    result['desempenho_publicado'] = performance
    result['jogos_agenda'] = len(fixtures)
    result['jogos_com_odds'] = len({row['evento_id'] for row in market_rows})
    return result


def download(report, label, key):
    st.download_button(label, json.dumps(report, ensure_ascii=False, indent=2, default=str),
                       file_name=f'{key}.json', mime='application/json', key=f'download_{key}')


def local_team_map():
    path = Path('reports/mapa_times_football_data_2026_2027.json')
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}


def latest_local_report(prefix, required):
    for path in sorted(Path('reports').glob(f'{prefix}_*.json'), reverse=True):
        try:
            report = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if isinstance(report, dict) and required.issubset(report):
            return report
    return None


with agenda_tab:
    st.subheader('Agenda e planejamento')
    today = datetime.now(ZoneInfo('America/Sao_Paulo')).date()
    st.write(f'Dia em São Paulo: {today:%d/%m/%Y}')
    if st.button('Atualizar agenda e planejar (2 consultas Football-data)'):
        try:
            with st.spinner('Consultando agenda e histórico local...'):
                captures = [collect('football-data', (today+timedelta(days=i)).isoformat()) for i in range(2)]
                st.session_state['capturas_integradas'] = captures
                st.session_state.pop('plano_integrado', None)
                db = store()
                st.session_state['plano_integrado'] = plan(captures, today, datetime.now(ZoneInfo('UTC')),
                    lambda season, league: read_csv(db, season, league), local_team_map())
        except (ValueError, DatabaseError):
            st.error('Não foi possível completar o planejamento. Confira os tokens, a cota e a conexão PostgreSQL local.')
    report = st.session_state.get('plano_integrado')
    if report:
        st.caption(f"Calculado em {report['calculado_em']}. Status: {report['status']}")
        if report['data'] != today.isoformat():
            st.warning('Relatório de outro dia; atualize antes de usar.')
        st.dataframe([{k:v for k,v in g.items() if k in ('id_api','inicio','mandante','visitante','status','motivo')} for g in report['jogos']], hide_index=True)
        for game in report['jogos']:
            if game.get('analise'):
                with st.expander(f"{game['mandante']} × {game['visitante']} — mercados"):
                    st.dataframe(game['analise']['mercados'], hide_index=True)
        st.write('Jogos na fila para consultar odds:', report['fila_betano'])
        queued = [g for g in report['jogos'] if g['id_api'] in report['fila_betano']
                  and datetime.fromisoformat(g['inicio']) > datetime.now(ZoneInfo('UTC'))]
        calculated = datetime.fromisoformat(report['calculado_em'])
        if queued and report['data'] == today.isoformat() and datetime.now(ZoneInfo('UTC')) - calculated <= timedelta(hours=1):
            selected = st.selectbox('Jogo para comparar odd informada', queued,
                                    format_func=lambda g: f"{g['mandante']} × {g['visitante']}",
                                    key='jogo_odd_integrado')
            market = st.selectbox('Mercado', selected['mercados_prioritarios'],
                                  format_func=lambda m: m['mercado'], key='mercado_odd_integrado')
            odd = st.number_input('Odd decimal conferida', min_value=1.01, value=1.50,
                                  step=0.01, key='odd_integrada')
            probability = market['probabilidade_estimada']
            st.write({'probabilidade_baseline': probability,
                      'ponto_equilibrio': 1 / odd,
                      'diferenca_estimativa_pontos_percentuais': 100 * (probability - 1 / odd),
                      'valor_esperado_teorico_por_real': probability * odd - 1})
            st.caption('Comparação descritiva com odd digitada. O baseline ainda não foi calibrado; diferença positiva não comprova vantagem.')
        elif report['fila_betano']:
            st.info('A fila está antiga ou os jogos já começaram. Atualize a agenda para comparar odds.')
        st.warning('Fila estatística não é indicação. A leitura automática dos mercados da Betano ainda não foi validada.')
        download(report, 'Baixar planejamento', 'planejamento')
with csv_tab:
    st.divider()
    st.subheader('Histórico europeu e validação')
    league = st.selectbox('Liga', list(LEAGUES), format_func=lambda k: LEAGUES[k])
    season = st.selectbox('Temporada', ['2026/2027','2025/2026'])
    try:
        data = read_csv(store(), season, league)
        total = data['resumo']['jogos']
        last_game = datetime.fromisoformat(data['resumo']['ultima_data'])
        observed = data['arquivo']['observado_em'].astimezone(ZoneInfo('America/Sao_Paulo'))
        summary_cols = st.columns(3)
        summary_cols[0].metric('Jogos no arquivo', total)
        summary_cols[1].metric('Último jogo registrado', last_game.strftime('%d/%m/%Y'))
        summary_cols[2].metric('Arquivo recebido em', observed.strftime('%d/%m/%Y'))
        if 'api.football-data.org' in data['arquivo']['origem']:
            st.caption('Placares fornecidos por football-data.org. Esta fonte cobre gols; escanteios, cartões e finalizações não estão disponíveis.')
        else:
            st.caption('Este é o CSV local da temporada escolhida. Para a agenda atual da Premier, use a aba “Premier e Brasileirão”.')
        with st.expander('Ver cobertura das estatísticas do arquivo'):
            st.write(f'“{total} de {total}” significa que todos os {total} jogos do CSV têm esse campo preenchido. Não é média de gols, escanteios ou finalizações.')
            st.dataframe([{'estatística': COVERAGE_LABELS.get(field, field),
                           'jogos com registro': f'{count} de {total}'}
                          for field, count in data['resumo']['cobertura_campos'].items()],
                         hide_index=True, width='stretch')
        teams = sorted({r[s] for r in data['partidas'] for s in ('mandante','visitante')})
        home = st.selectbox('Mandante', teams)
        away = st.selectbox('Visitante', teams, index=min(1,len(teams)-1))
        if st.button('Estudar mercados com o histórico disponível'):
            if home == away:
                st.error('Escolha equipes diferentes.')
            else:
                result = estimate(data['partidas'], home, away, today)
                st.dataframe(result['mercados'], hide_index=True)
                st.warning('Estudo hipotético, sem confirmação de partida na agenda. Amarelos não equivalem automaticamente ao total de cartões da casa.')
                download(result, 'Baixar estudo', 'estudo')
        if st.button('Avaliar over 2,5 em ordem cronológica'):
            with st.spinner('Avaliando partidas com dados de datas anteriores...'):
                evaluation = backtest(data['partidas'])
            st.write({k:v for k,v in evaluation.items() if k not in ('previsoes', 'calibracao_por_faixa')})
            if evaluation['calibracao_por_faixa']:
                st.caption('Por faixa de probabilidade estimada: média prevista versus frequência observada.')
                st.dataframe(evaluation['calibracao_por_faixa'], hide_index=True)
            if evaluation['supera_baseline_liga'] is False:
                st.warning('Nesta amostra o modelo não superou a frequência histórica da liga no Brier.')
            download(evaluation, 'Baixar avaliação histórica', 'avaliacao')
    except ValueError:
        st.info('O histórico europeu não está publicado neste banco. A fonte CSV usada no desenvolvimento não foi incluída na versão pública por restrições de uso e redistribuição.')
    except DatabaseError:
        st.error('Não foi possível consultar o PostgreSQL hospedado para carregar este histórico.')

with poisson_tab:
    st.divider()
    st.subheader('Poisson brasileiro')
    cid = st.number_input('ID do campeonato na API Dados Futebol', min_value=1, value=3)
    year = st.text_input('Temporada brasileira', value='2026')
    try:
        fixtures = upcoming(store(), int(cid), year)
        if not fixtures:
            st.info('Nenhuma partida futura no histórico local deste campeonato.')
        else:
            mid = st.selectbox('Partida local', [r['id'] for r in fixtures],
                format_func=lambda key: next(f"{r['mandante']} × {r['visitante']} — {r['data_hora']}" for r in fixtures if r['id']==key))
            if st.button('Calcular Poisson local'):
                result = forecast(store(), mid, int(cid), year)
                st.caption(f"Agenda observada em {result['agenda_observada_em']}; última coleta do treino: {result['amostra']['ultima_coleta_utilizada']}")
                st.dataframe([{'mercado':k,'probabilidade_modelo':v} for k,v in result['probabilidades'].items()], hide_index=True)
                st.warning('Estimativas experimentais. Dados antigos podem tornar a análise inadequada para uma aposta atual.')
                download(result, 'Baixar previsão', 'poisson')
    except (ValueError, DatabaseError):
        st.info('Não foi possível calcular com a amostra local. Verifique o banco, o campeonato e a cobertura.')

with focus_tab:
    st.subheader('Acompanhamento de gols')
    st.caption('Over 1,5 · over 2,5 · ambos marcam · Premier League e Brasileirão · próximos sete dias')
    st.info('As taxas abaixo descrevem jogos já encerrados na liga. Elas não são probabilidades calculadas para cada confronto.')
    if 'acompanhamento_foco' not in st.session_state:
        saved = latest_local_report('acompanhamento_foco',
            {'calculado_em', 'taxas', 'taxas_over_1_5', 'taxas_ambos_marcam', 'agenda_7_dias', 'qualidade_dados'})
        if saved:
            st.session_state['acompanhamento_foco'] = saved
            st.session_state['acompanhamento_foco_origem'] = 'relatório salvo'
    if st.button('Atualizar agenda e taxas', type='primary', help='Consulta uma vez a temporada atual da Premier e lê o Brasileirão no PostgreSQL.'):
        try:
            with st.spinner('Atualizando jogos e placares...'):
                db = store()
                brazil = read_brasileirao_goals(db, str(today.year))
                premier = collect_premier_season(today.year)
                now = datetime.now(ZoneInfo('UTC'))
                schedule = read_brasileirao_schedule(db, brazil['campeonato_id'], str(today.year), now)
                st.session_state['acompanhamento_foco'] = track_focus(premier, brazil, schedule, now)
                st.session_state['acompanhamento_foco_origem'] = 'consulta atual'
                st.session_state.pop('cotacao_foco', None)
        except (ValueError, DatabaseError):
            st.error('Acompanhamento indisponível. Confira chave Football-data, cota e PostgreSQL.')
    tracking = st.session_state.get('acompanhamento_foco')
    if tracking and 'taxas_over_1_5' not in tracking:
        saved = latest_local_report('acompanhamento_foco',
            {'calculado_em', 'taxas', 'taxas_over_1_5', 'taxas_ambos_marcam', 'agenda_7_dias', 'qualidade_dados'})
        tracking = saved
        if saved:
            st.session_state['acompanhamento_foco'] = saved
            st.session_state['acompanhamento_foco_origem'] = 'relatório salvo'
    if tracking:
        labels = {'premier_league': 'Premier League', 'brasileirao': 'Brasileirão'}
        market_labels = {'over_1_5': 'Mais de 1,5 gols',
                         'over': 'Mais de 2,5 gols', 'btts': 'Ambos marcam'}
        market_sources = (('over_1_5', 'taxas_over_1_5'),
                          ('over', 'taxas'), ('btts', 'taxas_ambos_marcam'))
        captured = datetime.fromisoformat(tracking['calculado_em']).astimezone(ZoneInfo('America/Sao_Paulo'))
        age = datetime.now(ZoneInfo('UTC')) - datetime.fromisoformat(tracking['calculado_em'])
        report_fresh = timedelta(0) <= age <= timedelta(hours=24)
        st.caption(f"{st.session_state.get('acompanhamento_foco_origem', 'relatório da sessão').capitalize()} · {captured:%d/%m/%Y às %H:%M} (São Paulo).")
        if not report_fresh:
            st.warning('Este relatório tem mais de 24 horas. Atualize a agenda para comparar cotações atuais.')
        for league in ('premier_league', 'brasileirao'):
            st.write(labels[league])
            cols = st.columns(3)
            for offset, (market, source) in enumerate(market_sources):
                rate = tracking[source][league]
                quality = tracking['qualidade_dados'][league]
                available = report_fresh and quality['captura_recente'] and quality['resultado_recente']
                value = f"{rate['taxa_suavizada']:.1%}" if available and rate['taxa_suavizada'] is not None else '—'
                cols[offset].metric(market_labels[market], value,
                    help=f"{rate['ocorrencias']} ocorrências em {rate['jogos']} jogos encerrados; frequência da liga, não previsão do confronto.")
        with st.expander('Cobertura e atualização das fontes'):
            st.dataframe([{'liga': labels[league], 'mercado': market_labels[market],
                           'jogos': tracking[source][league]['jogos'],
                           'ocorrências': tracking[source][league]['ocorrencias'],
                           'captura recente': tracking['qualidade_dados'][league]['captura_recente'],
                           'último resultado': tracking['qualidade_dados'][league]['ultimo_resultado']}
                          for league in labels
                          for market, source in market_sources],
                         hide_index=True, width='stretch')
        st.markdown('#### Próximos jogos')
        selected_league = st.selectbox('Liga da agenda', list(labels), format_func=lambda league: labels[league],
                                       key='liga_foco')
        fixtures = [game for game in tracking['agenda_7_dias'][selected_league]
                    if datetime.fromisoformat(game['inicio']) > datetime.now(ZoneInfo('UTC'))]
        if not fixtures:
            st.info('Nenhum jogo encontrado nos próximos sete dias para esta liga.')
        else:
            st.dataframe([{'início (São Paulo)': datetime.fromisoformat(game['inicio']).astimezone(
                              ZoneInfo('America/Sao_Paulo')).strftime('%d/%m %H:%M'),
                           'mandante': game['mandante'], 'visitante': game['visitante'],
                           'over 1,5 · liga': f"{game['taxa_liga_over_1_5']:.1%}" if report_fresh and game['taxa_liga_over_1_5'] is not None else '—',
                           'over 2,5 · liga': f"{game['taxa_liga_over_2_5']:.1%}" if report_fresh and game['taxa_liga_over_2_5'] is not None else '—',
                           'ambos marcam · liga': f"{game['taxa_liga_ambos_marcam']:.1%}" if report_fresh and game['taxa_liga_ambos_marcam'] is not None else '—',
                           'indicação': 'Nenhuma'} for game in fixtures],
                         hide_index=True, width='stretch')
            st.caption('A mesma taxa histórica da liga aparece em todos os seus jogos; ela não diferencia mandante e visitante.')
        st.warning('Nenhuma indicação de aposta: ainda faltam validação futura e odds pré-jogo alinhadas para os três mercados.')
        download(tracking, 'Baixar acompanhamento', 'acompanhamento_foco')
    else:
        st.caption('Clique em “Atualizar agenda e taxas” para carregar o acompanhamento atual.')
    st.divider()
    st.subheader('Desempenho histórico do modelo')
    st.caption('Brier menor é melhor. Cada previsão usa apenas jogos de datas anteriores.')
    if 'avaliacao_foco' not in st.session_state or 'gols_mais_1.5' not in st.session_state['avaliacao_foco'].get('mercados', []):
        saved_evaluation = latest_local_report('avaliacao_foco_premier_brasileirao', {'ligas', 'mercados'})
        if saved_evaluation and 'gols_mais_1.5' in saved_evaluation['mercados'] and all('avaliacoes' in item for item in saved_evaluation['ligas'].values()):
            st.session_state['avaliacao_foco'] = saved_evaluation
    if st.button('Avaliar históricos disponíveis no banco'):
        try:
            with st.spinner('Avaliando os três mercados nas ligas disponíveis...'):
                db = store()
                try:
                    premier_history = read_csv(db, '2025/2026', 'E0')
                except ValueError:
                    premier_history = None
                st.session_state['avaliacao_foco'] = evaluate_focus(
                    premier_history, read_brasileirao_goals(db, '2026'))
                if premier_history is None:
                    st.info('Premier 2025/26 sem histórico CSV neste banco. Avaliação brasileira disponível; a fonte europeia exige direitos de uso para publicação.')
        except DatabaseError:
            st.error('O aplicativo não conseguiu consultar o PostgreSQL hospedado. Confira o segredo FUTEBOL_DATABASE_URL e reinicie o app.')
        except ValueError as error:
            st.warning(f'Conexão estabelecida, mas o histórico brasileiro não pôde ser avaliado: {error}')
    focused = st.session_state.get('avaliacao_foco')
    if focused:
        st.dataframe([{'liga': {'premier_league': 'Premier League', 'brasileirao': 'Brasileirão'}[name],
                       'mercado': {'gols_mais_1.5': 'Mais de 1,5 gols',
                                   'gols_mais_2.5': 'Mais de 2,5 gols',
                                   'ambas_sim': 'Ambos marcam'}[market],
                       'jogos avaliados': evaluation['jogos_avaliados'],
                       'Brier · modelo': round(evaluation['brier_modelo'], 4) if evaluation['brier_modelo'] is not None else None,
                       'Brier · liga': round(evaluation['brier_baseline_liga'], 4) if evaluation['brier_baseline_liga'] is not None else None,
                       'superou a liga': evaluation['supera_baseline_liga']}
                      for name, item in focused['ligas'].items()
                      for market, evaluation in item['avaliacoes'].items()],
                     hide_index=True, width='stretch')
        if 'premier_league' in focused['ligas']:
            st.caption('Premier: CSV 2025/26. Brasileirão: jogos de 2026. A avaliação usa as versões atuais dessas fontes.')
        else:
            st.caption('Avaliação baseada nos jogos disponíveis do Brasileirão 2026. O histórico europeu não está publicado neste banco.')
        st.warning('O modelo não está aprovado para indicações. Compare o Brier do modelo com a referência simples da liga.')
        download(focused, 'Baixar avaliação', 'avaliacao_foco')

with decision_tab:
    st.divider()
    st.subheader('Painel de decisão')
    st.caption('Probabilidades por jogo, validação do modelo e controle de exposição. Ler dados armazenados não consome créditos.')
    with st.expander('Política de risco usada pelo painel'):
        st.markdown('''
- **Sem validação, sem aposta:** mercado que não supera a referência da liga recebe exposição zero.
- **Uma seleção por jogo:** evita somar apostas fortemente correlacionadas.
- **Até 1% da banca por aposta e 3% no dia:** limites conservadores ajustáveis para baixo.
- **Um quarto de Kelly:** reduz a sensibilidade a erros na probabilidade estimada.
- **Sem recuperação de perdas:** o valor não aumenta depois de um resultado negativo.
''')
    odds_league = st.selectbox('Liga do painel', ['premier_league', 'brasileirao'],
                               format_func=lambda value: {'premier_league': 'Premier League',
                                                          'brasileirao': 'Brasileirão'}[value])
    if st.button('Atualizar painel de jogos', type='primary'):
        try:
            with st.spinner('Lendo agenda, histórico e odds armazenadas...'):
                db = store()
                market_rows = upcoming_odds(db, odds_league)
                result = calculate_decision(db, odds_league, today, market_rows)
                st.session_state['odds_proximos'] = market_rows
                st.session_state['odds_proximos_liga'] = odds_league
                st.session_state['ranking_oportunidades'] = result
                st.session_state['ranking_oportunidades_liga'] = odds_league
        except (ValueError, DatabaseError):
            st.error('Não foi possível atualizar o painel. Confira a agenda, o histórico e o PostgreSQL.')
    market_rows = (st.session_state.get('odds_proximos')
                   if st.session_state.get('odds_proximos_liga') == odds_league else None)
    if market_rows is not None:
        if market_rows:
            grouped_market = {}
            for row in market_rows:
                item = grouped_market.setdefault(row['evento_id'], {
                    'início': row['inicio'].astimezone(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m %H:%M'),
                    'jogo': f"{row['mandante']} × {row['visitante']}",
                    'mandante': row['mandante'], 'visitante': row['visitante']})
                probability = 100 * row['probabilidade_justa']
                selection = row['selecao'].casefold()
                if row['mercado'] == 'h2h':
                    if selection == 'draw': item['empate · mercado'] = probability
                    elif row['selecao'] == row['mandante']: item['vitória mandante · mercado'] = probability
                    elif row['selecao'] == row['visitante']: item['vitória visitante · mercado'] = probability
                elif row['mercado'] in ('totals', 'alternate_totals') and selection == 'over':
                    if row['linha'] == 1.5: item['+1,5 · mercado'] = probability
                    elif row['linha'] == 2.5: item['+2,5 · mercado'] = probability
                elif row['mercado'] == 'btts' and selection in ('yes', 'sim'):
                    item['ambos marcam · mercado'] = probability
            latest_quote = max(row['observado_em'] for row in market_rows)
            overview = st.columns(4)
            overview[0].metric('Jogos encontrados', len(grouped_market))
            overview[1].metric('Registros consolidados', len(market_rows))
            overview[2].metric('Última cotação', latest_quote.astimezone(
                ZoneInfo('America/Sao_Paulo')).strftime('%d/%m %H:%M'))
            overview[3].metric('Mercados do modelo', '3')
            st.markdown('##### Probabilidades implícitas nas odds das casas')
            market_summary = [{key: value for key, value in item.items()
                               if key not in ('mandante', 'visitante')}
                              for item in grouped_market.values()]
            probability_columns = ('vitória mandante · mercado', 'empate · mercado',
                'vitória visitante · mercado', '+1,5 · mercado', '+2,5 · mercado',
                'ambos marcam · mercado')
            formatted_summary = []
            for item in market_summary:
                row = {key: item.get(key) for key in ('início', 'jogo')}
                for name in probability_columns:
                    value = item.get(name)
                    row[name] = f'{value:.1f}%' if value is not None else '—'
                extras = sum(item.get(name) is not None
                             for name in ('+1,5 · mercado', 'ambos marcam · mercado'))
                row['cobertura adicional'] = 'completa' if extras == 2 else 'parcial' if extras else 'não coletada'
                formatted_summary.append(row)
            st.dataframe(formatted_summary, hide_index=True, width='stretch')
            st.caption('Estas porcentagens vêm das odds das casas após remover a margem; não usam a média de gols do nosso modelo. “—” significa que a cotação adicional não foi coletada, não 0%.')
            with st.expander('Dados técnicos das odds'):
                st.caption(f"{len(market_rows)} registros de mercado consolidados em {len(grouped_market)} jogos. A tabela repetida por seleção foi removida da interface.")
                download(market_rows, 'Baixar odds detalhadas', f'odds_detalhadas_{odds_league}')
        else:
            st.info('Nenhuma odd futura foi encontrada. O modelo ainda pode calcular os jogos presentes na agenda.')
        st.markdown('#### Probabilidades calculadas pelo histórico')
        st.caption('Nosso modelo usa até 20 jogos anteriores por contexto, separa mandante em casa e visitante fora, pondera jogos recentes e regulariza pela média da liga.')
        if st.button('Recalcular modelo com os dados armazenados'):
            try:
                with st.spinner('Calculando previsões e validação cronológica...'):
                    db = store()
                    result = calculate_decision(db, odds_league, today, market_rows)
                    st.session_state['ranking_oportunidades'] = result
                    st.session_state['ranking_oportunidades_liga'] = odds_league
            except (ValueError, DatabaseError) as error:
                st.warning(f'Não foi possível concluir o ranking: {error}')
        ranking = (st.session_state.get('ranking_oportunidades')
                   if st.session_state.get('ranking_oportunidades_liga') == odds_league else None)
        if ranking:
            if ranking.get('resumo_jogos'):
                approved_markets = sum(item['aprovado'] for item in ranking['validacoes'].values())
                st.markdown('##### Nosso modelo · uma linha por jogo')
                st.caption(f"Agenda encontrada: {ranking.get('jogos_agenda', 0)} jogo(s) · com odds armazenadas: {ranking.get('jogos_com_odds', 0)}. As probabilidades históricas independem das odds; a análise de valor exige preço de mercado.")
                if approved_markets:
                    st.success(f'{approved_markets} mercado(s) superaram a referência histórica nesta validação.')
                else:
                    st.warning('Modelo experimental: nenhum mercado superou a referência simples da liga. Use as probabilidades para acompanhamento, não como indicação.')
                st.dataframe([{
                    'início': item['inicio'].astimezone(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m %H:%M'),
                    'jogo': f"{item['mandante']} × {item['visitante']}",
                    'fonte da agenda': {'dados-futebol': 'Dados Futebol', 'football-data': 'Football-Data',
                                        'odds': 'The Odds API'}.get(item.get('origem_agenda'), 'Agenda'),
                    'situação': item['estado_decisao'],
                    'qualidade': item['qualidade_dados'],
                    'odds': item['cobertura_mercado'],
                    'vitória · mandante': 100 * item['vitoria_mandante'],
                    'empate': 100 * item['empate'],
                    'vitória · visitante': 100 * item['vitoria_visitante'],
                    'mais de 1,5 gols': 100 * item['over_1.5'],
                    'mais de 2,5 gols': 100 * item['over_2.5'],
                    'ambos marcam': 100 * item['ambas_marcam'],
                    'média gols · casa/fora': f"{item['media_gols_recente_casa']:.2f} / {item['media_gols_recente_fora']:.2f}",
                    'gols esperados': f"{item['gols_esperados_mandante']:.2f} × {item['gols_esperados_visitante']:.2f}",
                    'confiança': item['confianca'],
                    'amostra casa/fora': f"{item['amostra_mandante']}/{item['amostra_visitante']}",
                } for item in ranking['resumo_jogos']], hide_index=True, width='stretch',
                    column_config={name: st.column_config.NumberColumn(format='%.1f%%')
                                   for name in ('vitória · mandante', 'empate',
                                                'vitória · visitante', 'mais de 1,5 gols',
                                                'mais de 2,5 gols', 'ambos marcam',
                                                )})
                st.caption(f"Probabilidades registradas antes dos jogos: {ranking.get('previsoes_registradas', 0)}. Qualidade descreve cobertura e tamanho da amostra; não representa certeza do resultado.")
                selected_game = st.selectbox('Detalhar partida', ranking['resumo_jogos'],
                    format_func=lambda item: f"{item['mandante']} × {item['visitante']} · {item['estado_decisao']}",
                    key=f'detalhe_partida_{odds_league}')
                with st.expander('Diagnóstico da partida', expanded=True):
                    detail_metrics = st.columns(4)
                    detail_metrics[0].metric('Gols esperados',
                        f"{selected_game['gols_esperados_mandante'] + selected_game['gols_esperados_visitante']:.2f}")
                    detail_metrics[1].metric('Amostra casa/fora',
                        f"{selected_game['amostra_mandante']}/{selected_game['amostra_visitante']}")
                    detail_metrics[2].metric('Qualidade', selected_game['qualidade_dados'])
                    detail_metrics[3].metric('Situação', selected_game['estado_decisao'])
                    st.write('**Motivos da decisão:** ' + '; '.join(selected_game['motivos_decisao']))
                    st.dataframe([{'mercado': 'Vitória do mandante', 'probabilidade': 100 * selected_game['vitoria_mandante']},
                                  {'mercado': 'Empate', 'probabilidade': 100 * selected_game['empate']},
                                  {'mercado': 'Vitória do visitante', 'probabilidade': 100 * selected_game['vitoria_visitante']},
                                  {'mercado': 'Mais de 1,5 gols', 'probabilidade': 100 * selected_game['over_1.5']},
                                  {'mercado': 'Mais de 2,5 gols', 'probabilidade': 100 * selected_game['over_2.5']},
                                  {'mercado': 'Ambos marcam', 'probabilidade': 100 * selected_game['ambas_marcam']}],
                                 hide_index=True, width='stretch',
                                 column_config={'probabilidade': st.column_config.ProgressColumn(
                                     min_value=0, max_value=100, format='%.1f%%')})
                    if selected_game['estado_decisao'] == 'sem preço de mercado':
                        st.info('Existe previsão histórica, mas ainda não há preço para medir valor esperado.')
                    elif selected_game['estado_decisao'] == 'sem valor validado':
                        st.info('Há odds, mas nenhuma seleção passou simultaneamente pela validação, vantagem e valor esperado mínimos.')
                with st.expander('Como interpretar esta tabela'):
                    st.write('Vitória do mandante, empate e vitória do visitante somam 100%. Mais de 1,5, mais de 2,5 e ambos marcam são mercados separados e não devem ser somados.')
                    st.write('O modelo pondera partidas recentes com meia-vida de 180 dias e regulariza amostras pequenas pela média da liga.')
                published = ranking.get('desempenho_publicado', {})
                if published.get('desempenho'):
                    with st.expander('Desempenho das previsões realmente registradas'):
                        st.caption(f"Previsões avaliadas nesta execução: {published.get('avaliadas_agora', 0)}. Diferente do backtest, estas previsões foram armazenadas antes das partidas.")
                        st.dataframe(published['desempenho'], hide_index=True, width='stretch',
                            column_config={'brier': st.column_config.NumberColumn(format='%.4f')})
                        calibration = published.get('calibracao_geral') or {}
                        if calibration.get('avaliadas'):
                            calibration_metrics = st.columns(4)
                            calibration_metrics[0].metric('Previsões avaliadas', calibration['avaliadas'])
                            calibration_metrics[1].metric('Brier', f"{calibration['brier']:.4f}")
                            calibration_metrics[2].metric('Log Loss', f"{calibration['log_loss']:.4f}")
                            calibration_metrics[3].metric('Erro de calibração',
                                                          f"{calibration['erro_calibracao']:.1%}")
                            st.caption('O erro de calibração compara a probabilidade média prevista com a frequência observada em faixas de 10 pontos percentuais; menor é melhor.')
                            st.dataframe(calibration['faixas'], hide_index=True, width='stretch',
                                column_config={name: st.column_config.NumberColumn(format='%.1f%%')
                                    for name in ('probabilidade_media', 'frequencia_observada',
                                                 'erro_absoluto')})
                        closing = published.get('closing_line_value') or {}
                        if closing.get('comparacoes'):
                            st.markdown('###### Qualidade do preço · fechamento')
                            closing_metrics = st.columns(3)
                            closing_metrics[0].metric('Comparações', closing['comparacoes'])
                            closing_metrics[1].metric('CLV médio', f"{closing['clv_medio']:.2%}")
                            closing_metrics[2].metric('Superou o fechamento',
                                                      f"{closing['percentual_superou_fechamento']:.1%}")
                            st.caption('CLV = odd observada na previsão ÷ odd mediana de fechamento − 1. Valor positivo indica que o preço observado foi melhor que o fechamento; isso não mede lucro realizado.')
                        else:
                            st.caption('CLV ainda sem amostra: ele aparecerá quando previsões com odd registrada também tiverem consenso de fechamento.')
                strategy = ranking.get('desempenho_estrategia') or {}
                with st.expander('Diário automático da estratégia'):
                    strategy_cols = st.columns(4)
                    strategy_cols[0].metric('Decisões', strategy.get('decisoes', 0))
                    strategy_cols[1].metric('Liquidadas', strategy.get('liquidadas', 0))
                    strategy_cols[2].metric('Yield', f"{strategy['yield']:.1%}" if strategy.get('yield') is not None else '—')
                    strategy_cols[3].metric('Drawdown máximo', f"{strategy.get('drawdown_maximo', 0):.2%}")
                    st.caption('Registra automaticamente apenas seleções que passaram por todas as travas. Os valores usam frações teóricas da banca e não representam apostas pessoais.')
            validation_rows = [{
                'mercado': {'over_1.5': 'Mais de 1,5 gols', 'over_2.5': 'Mais de 2,5 gols',
                            'ambas_marcam': 'Ambos marcam'}[key],
                'jogos avaliados': item['jogos_avaliados'],
                'Brier · modelo': item['brier_modelo'], 'Brier · liga': item['brier_liga'],
                'Log Loss · modelo': item['log_loss_modelo'],
                'Log Loss · liga': item['log_loss_liga'],
                'estável nos períodos': item['estavel_nos_dois_periodos'],
                'estado': item['estado'],
                'aprovado': item['aprovado']}
                for key, item in ranking['validacoes'].items()]
            st.dataframe(validation_rows, hide_index=True, width='stretch',
                column_config={'Brier · modelo': st.column_config.NumberColumn(format='%.4f'),
                               'Brier · liga': st.column_config.NumberColumn(format='%.4f'),
                               'Log Loss · modelo': st.column_config.NumberColumn(format='%.4f'),
                               'Log Loss · liga': st.column_config.NumberColumn(format='%.4f')})
            if ranking['oportunidades']:
                st.dataframe([{
                    'início': item['inicio'].astimezone(ZoneInfo('America/Sao_Paulo')).strftime('%d/%m %H:%M'),
                    'jogo': item['jogo'], 'mercado': item['mercado'],
                    'probabilidade · modelo': 100 * item['probabilidade_modelo'],
                    'probabilidade · mercado': 100 * item['probabilidade_mercado'],
                    'vantagem · p.p.': 100 * item['vantagem'],
                    'melhor odd observada': item['odd_referencia'],
                    'valor esperado · por R$ 1': item['valor_esperado'], 'casas': item['casas']}
                    for item in ranking['oportunidades']], hide_index=True, width='stretch',
                    column_config={
                        'probabilidade · modelo': st.column_config.NumberColumn(format='%.1f%%'),
                        'probabilidade · mercado': st.column_config.NumberColumn(format='%.1f%%'),
                        'vantagem · p.p.': st.column_config.NumberColumn(format='%+.1f'),
                        'melhor odd observada': st.column_config.NumberColumn(format='%.2f'),
                        'valor esperado · por R$ 1': st.column_config.NumberColumn(format='%+.3f')})
                with st.expander('Plano conservador de exposição'):
                    st.caption('O cálculo limita concentração, usa um quarto de Kelly e escolhe no máximo um mercado por jogo. Não recupera perdas aumentando apostas.')
                    bankroll = st.number_input('Banca de referência (R$)', min_value=50.0,
                        value=1000.0, step=50.0, key='banca_risco')
                    risk_cols = st.columns(2)
                    max_bet = risk_cols[0].slider('Máximo por aposta', min_value=0.25,
                        max_value=2.0, value=1.0, step=0.25, format='%.2f%%') / 100
                    max_day = risk_cols[1].slider('Máximo no dia', min_value=0.5,
                        max_value=5.0, value=3.0, step=0.5, format='%.1f%%') / 100
                    exposure = risk_plan(ranking['oportunidades'], bankroll=bankroll,
                        max_bet_fraction=max_bet, max_daily_fraction=max_day)
                    st.metric('Exposição máxima desta seleção',
                              f"R$ {exposure['exposicao_total']:.2f}",
                              help=f"{exposure['fracao_total']:.2%} da banca informada")
                    st.dataframe([{'jogo': item['jogo'], 'mercado': item['mercado'],
                        'odd de referência': item['odd_referencia'],
                        'probabilidade modelo': 100 * item['probabilidade_modelo'],
                        'limite da aposta': item['valor_maximo'],
                        '% da banca': 100 * item['fracao_banca']}
                        for item in exposure['selecoes']], hide_index=True, width='stretch',
                        column_config={'odd de referência': st.column_config.NumberColumn(format='%.2f'),
                            'probabilidade modelo': st.column_config.NumberColumn(format='%.1f%%'),
                            'limite da aposta': st.column_config.NumberColumn(format='R$ %.2f'),
                            '% da banca': st.column_config.NumberColumn(format='%.2f%%')})
                    st.warning('Limite de exposição não transforma uma estimativa em aposta segura. Pare ao atingir o limite diário e não use crédito ou dinheiro destinado a despesas.')
            else:
                st.info('Nenhuma oportunidade passou por todas as travas neste momento.')
                st.caption('Proteção de banca aplicada: sem mercado validado, a exposição recomendada é R$ 0,00.')
            if ranking['eventos_sem_modelo']:
                st.caption(f"{len(ranking['eventos_sem_modelo'])} jogo(s) ficaram sem modelo por falta de histórico ou associação segura das equipes.")
            st.warning(ranking['aviso'])
        event_ids = ranking.get('pre_selecao_eventos', []) if ranking else []
        if event_ids:
            st.caption(f'Consulta opcional de ambos marcam e linhas alternativas para os {len(event_ids)} jogos com maior divergência preliminar: custo estimado de {len(event_ids) * 2} créditos.')
        else:
            st.caption('Analise as oportunidades primeiro para formar a pré-seleção dos mercados adicionais.')
        if event_ids and st.button('Buscar ambos marcam e over 1,5 da pré-seleção'):
            try:
                with st.spinner('Consultando mercados adicionais dos jogos pré-selecionados...'):
                    db = store()
                    capture = collect_event_odds(odds_league, event_ids)
                    saved = save_odds(db, capture)
                    st.session_state['odds_proximos'] = upcoming_odds(db, odds_league)
                    st.session_state.pop('ranking_oportunidades', None)
                    st.success(f"Mercados adicionais armazenados para {saved['eventos']} jogos. Refaça o ranking.")
                    if capture.get('falhas'):
                        st.warning(f"Algumas combinações não estavam disponíveis ({len(capture['falhas'])} de {len(event_ids) * 2}). Os resultados disponíveis foram preservados.")
                        with st.expander('Ver mercados indisponíveis'):
                            st.dataframe(capture['falhas'], hide_index=True, width='stretch')
            except ValueError as error:
                st.error(f'A consulta direcionada falhou: {error}')
            except DatabaseError:
                st.error('A consulta respondeu, mas não foi possível armazenar o resultado no PostgreSQL.')
    st.caption('A coleta manual abaixo consome créditos. A leitura da tabela acima usa somente o Neon.')
    if st.button('Coletar e armazenar odds'):
        try:
            with st.spinner('Consultando e normalizando as cotações...'):
                db = store()
                db.initialize()
                capture = collect_odds(odds_league)
                saved = save_odds(db, capture)
                st.session_state['odds_ultima_coleta'] = {**saved,
                    'liga': odds_league, 'creditos_restantes': capture['creditos_restantes'],
                    'capturado_em': capture['capturado_em']}
        except (ValueError, DatabaseError):
            st.error('Não foi possível coletar as odds. Confira THE_ODDS_API_KEY, mercados, cota e banco.')
    if st.session_state.get('odds_ultima_coleta'):
        st.success('Odds normalizadas e armazenadas.')
        st.write(st.session_state['odds_ultima_coleta'])
    st.info('Os consensos de abertura, 24 horas e fechamento são permanentes. JSON bruto: 7 dias; detalhes por casa: 30 dias.')

with database_tab:
    st.subheader('Armazenamento do PostgreSQL')
    st.caption('O percentual usa 0,5 GB como referência do plano gratuito atual do Neon.')
    if st.button('Medir uso do banco'):
        try:
            st.session_state['relatorio_armazenamento'] = storage_report(store())
        except DatabaseError:
            st.error('Não foi possível medir o banco hospedado.')
    database_usage = st.session_state.get('relatorio_armazenamento')
    if database_usage:
        st.write({
            'uso total': f"{database_usage['total_bytes'] / 1_000_000:.2f} MB",
            'percentual da referência': f"{database_usage['percentual_limite']:.1f}%",
            'nível': database_usage['nivel'],
        })
        st.progress(min(database_usage['percentual_limite'] / 100, 1.0))
        st.dataframe([{'tabela': row['tabela'], 'tamanho': f"{row['bytes'] / 1_000_000:.2f} MB"}
                      for row in database_usage['tabelas']], hide_index=True, width='stretch')
