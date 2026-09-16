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
from futebol_analytics.analysis.quote_check import check_quote
from futebol_analytics.api.league import collect_premier_season
from futebol_analytics.analysis.multimarket import estimate
from futebol_analytics.config.settings import load_database_settings
from futebol_analytics.database.store import SnapshotStore, DatabaseError
from futebol_analytics.database.csv_store import read_csv
from futebol_analytics.database.forecast import upcoming, forecast
from futebol_analytics.database.league_rows import read_brasileirao_goals, read_brasileirao_schedule
from futebol_analytics.daily import plan


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
focus_tab, agenda_tab, csv_tab, poisson_tab = st.tabs([
    'Premier e Brasileirão', 'Agenda e planejamento',
    'Histórico europeu e validação', 'Poisson brasileiro'])


def store():
    return SnapshotStore(load_database_settings())


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
    if st.button('Consultar Sportmonks hoje (ligas gratuitas)'):
        try:
            st.session_state['sportmonks_integrado'] = collect('sportmonks', today.isoformat())
        except ValueError:
            st.error('Consulta Sportmonks não concluída. Confira token, cobertura e cota.')
    if 'sportmonks_integrado' in st.session_state:
        sport = st.session_state['sportmonks_integrado']
        st.caption(f"Consulta UTC: {sport['data_utc']}; coletado em {sport['fim_coleta']}")
        st.dataframe([{'jogo':r.get('name'), 'inicio_utc':r.get('starting_at'), 'estado':(r.get('state') or {}).get('name'),
                       'registros_estatisticos':len(r.get('statistics') or [])} for r in sport['partidas']], hide_index=True)
        download(sport, 'Baixar resposta Sportmonks', 'sportmonks')

with csv_tab:
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
    except (ValueError, DatabaseError):
        st.info('Histórico local indisponível para esta seleção. Confira o PostgreSQL e a importação da temporada.')

with poisson_tab:
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
            with st.expander('Conferir uma odd deste jogo'):
                if not report_fresh:
                    st.info('Atualize a agenda e as taxas antes de conferir uma odd atual.')
                else:
                    st.caption('Digite uma cotação pré-jogo atual para ver o ponto de equilíbrio. A comparação com a taxa histórica não comprova vantagem.')
                    with st.form('conferir_odd_foco'):
                        selected_game = st.selectbox('Jogo', fixtures,
                            format_func=lambda game: f"{game['mandante']} × {game['visitante']} · {datetime.fromisoformat(game['inicio']).astimezone(ZoneInfo('America/Sao_Paulo')):%d/%m %H:%M}")
                        selected_market = st.selectbox('Mercado', list(market_labels),
                            format_func=lambda market: market_labels[market])
                        quote_source = st.text_input('Fonte da cotação', value='Betano')
                        quoted_odd = st.number_input('Odd decimal atual', min_value=1.01, value=1.80, step=0.01)
                        submitted = st.form_submit_button('Conferir cotação')
                    if submitted:
                        field = {'over_1_5': 'taxa_liga_over_1_5',
                                 'over': 'taxa_liga_over_2_5',
                                 'btts': 'taxa_liga_ambos_marcam'}[selected_market]
                        st.session_state['cotacao_foco'] = {
                            'liga': selected_league, 'jogo_id': selected_game['id'],
                            'jogo': f"{selected_game['mandante']} × {selected_game['visitante']}",
                            'mercado': market_labels[selected_market], 'fonte': quote_source.strip(),
                            'informado_em': datetime.now(ZoneInfo('America/Sao_Paulo')).isoformat(),
                            **check_quote(quoted_odd, selected_game[field])}
                    quote_result = st.session_state.get('cotacao_foco')
                    if quote_result and quote_result['liga'] == selected_league:
                        st.write(f"{quote_result['jogo']} · {quote_result['mercado']} · {quote_result['fonte'] or 'fonte não informada'}")
                        st.write(f"Odd {quote_result['odd_decimal']:.2f}: precisa de mais de {quote_result['probabilidade_equilibrio']:.1%} de acerto para ter valor esperado positivo.")
                        if quote_result['taxa_historica_liga'] is not None:
                            st.write(f"Frequência histórica da liga: {quote_result['taxa_historica_liga']:.1%}. Diferença descritiva: {quote_result['diferenca_descritiva_pontos_percentuais']:+.1f} pontos percentuais.")
                        st.warning(quote_result['motivo'])
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
        st.caption('Premier: CSV 2025/26 quando disponível. Brasileirão: jogos locais de 2026. A avaliação usa as versões atuais dessas fontes.')
        st.warning('O modelo não está aprovado para indicações. Compare o Brier do modelo com a referência simples da liga.')
        download(focused, 'Baixar avaliação das duas ligas', 'avaliacao_foco')
