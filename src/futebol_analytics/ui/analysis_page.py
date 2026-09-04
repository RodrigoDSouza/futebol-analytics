"""Conteúdo da página de análises do Futebol Analytics."""

from typing import Any

import streamlit as st

from futebol_analytics.analysis.team_form import (
    SemPartidasEncerradasError,
    analisar_forma_time,
)
from futebol_analytics.analysis.matchup import comparar_mandante_visitante
from futebol_analytics.analysis.odds import (
    analisar_mercado_1x2,
    analisar_mercado_duas_vias,
)
from futebol_analytics.analysis.round_radar import gerar_radar_rodada
from futebol_analytics.api.exceptions import DadosFutebolError
from futebol_analytics.config.settings import ConfigurationError
from futebol_analytics.ui.data import (
    carregar_campeonatos,
    carregar_rodadas,
    formatar_horario_atualizacao,
)
from futebol_analytics.services.rodadas import (
    ProximaRodadaNaoEncontradaError,
    localizar_proxima_rodada,
)


def extrair_times(rodadas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extrai times únicos das partidas e os ordena pelo nome."""
    times_por_id: dict[int, dict[str, Any]] = {}

    for rodada in rodadas:
        for partida in rodada.get("partidas", []):
            for campo in ("time_mandante", "time_visitante"):
                time = partida.get(campo)
                if isinstance(time, dict) and isinstance(time.get("id"), int):
                    times_por_id[time["id"]] = time

    return sorted(times_por_id.values(), key=lambda time: time.get("nome", ""))


def mostrar_relatorio(relatorio: dict[str, Any]) -> None:
    """Apresenta as métricas calculadas sem realizar novos cálculos ou chamadas."""
    st.subheader("Forma recente")
    st.caption(
        f"{relatorio['jogos_analisados']} jogos encerrados · "
        f"recorte: {relatorio['mando']}"
    )

    coluna_1, coluna_2, coluna_3, coluna_4 = st.columns(4)
    coluna_1.metric("Vitórias", relatorio["vitorias"])
    coluna_2.metric("Empates", relatorio["empates"])
    coluna_3.metric("Derrotas", relatorio["derrotas"])
    coluna_4.metric("Sequência", " · ".join(relatorio["sequencia_recente"]))

    coluna_1, coluna_2, coluna_3, coluna_4 = st.columns(4)
    coluna_1.metric("Gols marcados", relatorio["gols_marcados"])
    coluna_2.metric("Gols sofridos", relatorio["gols_sofridos"])
    coluna_3.metric("Média marcados", relatorio["media_gols_marcados"])
    coluna_4.metric("Média sofridos", relatorio["media_gols_sofridos"])

    ocorrencias = [
        {
            "Indicador": "Over 1.5",
            **relatorio["over_1_5"],
        },
        {
            "Indicador": "Over 2.5",
            **relatorio["over_2_5"],
        },
        {
            "Indicador": "Ambas marcam",
            **relatorio["ambas_marcam"],
        },
        {
            "Indicador": "Clean sheets",
            **relatorio["clean_sheets"],
        },
    ]
    st.dataframe(
        ocorrencias,
        column_config={
            "quantidade": st.column_config.NumberColumn("Ocorrências"),
            "percentual": st.column_config.ProgressColumn(
                "Percentual",
                min_value=0,
                max_value=100,
                format="%.1f%%",
            ),
        },
        hide_index=True,
        width="stretch",
    )

    st.subheader("Últimos resultados utilizados")
    partidas = relatorio.get("partidas_consideradas", [])
    if partidas:
        st.dataframe(
            partidas,
            column_config={
                "data": st.column_config.TextColumn("Data"),
                "data_hora": None,
                "mandante": st.column_config.TextColumn("Mandante"),
                "visitante": st.column_config.TextColumn("Visitante"),
                "placar": st.column_config.TextColumn("Placar"),
                "resultado_time": st.column_config.TextColumn("Resultado"),
            },
            hide_index=True,
            width="stretch",
        )
    else:
        st.info("Nenhuma partida foi incluída neste relatório.")


def mostrar_resumo_time(nome: str, relatorio: dict[str, Any]) -> None:
    """Mostra um resumo compacto para um participante da comparação."""
    st.markdown(f"### {nome}")
    st.caption(f"Recorte: {relatorio['mando']}")
    st.metric("Campanha", f"{relatorio['vitorias']}V · {relatorio['empates']}E · {relatorio['derrotas']}D")
    coluna_1, coluna_2 = st.columns(2)
    coluna_1.metric("Gols marcados/jogo", relatorio["media_gols_marcados"])
    coluna_2.metric("Gols sofridos/jogo", relatorio["media_gols_sofridos"])
    st.write(
        {
            "Over 1.5": f"{relatorio['over_1_5']['percentual']}%",
            "Over 2.5": f"{relatorio['over_2_5']['percentual']}%",
            "Ambas marcam": f"{relatorio['ambas_marcam']['percentual']}%",
            "Clean sheets": f"{relatorio['clean_sheets']['percentual']}%",
        }
    )
    with st.expander("Ver jogos utilizados"):
        partidas = relatorio.get("partidas_consideradas", [])
        if partidas:
            st.dataframe(
                partidas,
                hide_index=True,
                width="stretch",
            )
        else:
            st.caption("Recalcule a análise para carregar os jogos utilizados.")


def mostrar_confrontos_diretos(
    nome_mandante: str,
    nome_visitante: str,
    confrontos: dict[str, Any],
) -> None:
    """Mostra os confrontos disponíveis no campeonato carregado."""
    st.subheader("Confrontos diretos")
    total = confrontos["jogos_analisados"]
    if total == 0:
        st.warning(
            "Não há confrontos encerrados entre estes times na temporada e "
            "no campeonato carregados."
        )
        return

    st.caption(f"{total} confronto(s) encontrado(s) no campeonato atual")
    coluna_1, coluna_2, coluna_3 = st.columns(3)
    coluna_1.metric(f"Vitórias · {nome_mandante}", confrontos["vitorias_time_a"])
    coluna_2.metric("Empates", confrontos["empates"])
    coluna_3.metric(f"Vitórias · {nome_visitante}", confrontos["vitorias_time_b"])

    coluna_1, coluna_2, coluna_3 = st.columns(3)
    coluna_1.metric("Over 1.5", f"{confrontos['over_1_5_percentual']}%")
    coluna_2.metric("Over 2.5", f"{confrontos['over_2_5_percentual']}%")
    coluna_3.metric("Ambas marcam", f"{confrontos['ambas_marcam_percentual']}%")
    partidas = confrontos.get("partidas_consideradas", [])
    if partidas:
        st.dataframe(
            partidas,
            hide_index=True,
        width="stretch",
    )


def mostrar_simulador_duas_vias(
    *,
    titulo: str,
    opcao_a: str,
    opcao_b: str,
    chave: str,
) -> None:
    """Renderiza e calcula um mercado manual com duas opções."""
    st.markdown(f"#### {titulo}")
    coluna_1, coluna_2 = st.columns(2)
    odd_a = coluna_1.number_input(
        f"Odd · {opcao_a}",
        min_value=1.01,
        value=1.90,
        step=0.01,
        format="%.2f",
        key=f"{chave}_a",
    )
    odd_b = coluna_2.number_input(
        f"Odd · {opcao_b}",
        min_value=1.01,
        value=1.90,
        step=0.01,
        format="%.2f",
        key=f"{chave}_b",
    )
    mercado = analisar_mercado_duas_vias(
        nome_opcao_a=opcao_a,
        odd_opcao_a=odd_a,
        nome_opcao_b=opcao_b,
        odd_opcao_b=odd_b,
    )
    st.dataframe(
        [
            {
                "Opção": nome,
                "Odd": mercado["odds"][nome],
                "Implícita": mercado["probabilidades_implicitas"][nome],
                "Normalizada": mercado["probabilidades_normalizadas"][nome],
            }
            for nome in (opcao_a, opcao_b)
        ],
        column_config={
            "Implícita": st.column_config.NumberColumn(format="%.2f%%"),
            "Normalizada": st.column_config.NumberColumn(format="%.2f%%"),
        },
        hide_index=True,
        width="stretch",
    )
    st.caption(
        f"Soma implícita: {mercado['soma_probabilidades']}% · "
        f"margem teórica: {mercado['margem_teorica']}%"
    )


def main() -> None:
    st.write("Análise estatística de partidas encerradas do futebol brasileiro.")

    try:
        with st.spinner("Consultando campeonatos..."):
            campeonatos = carregar_campeonatos()

        if not campeonatos:
            st.warning("Nenhum campeonato foi retornado pela API.")
            return

        campeonato = st.selectbox(
            "Campeonato",
            campeonatos,
            format_func=lambda item: f"{item['nome']} · {item['temporada']}",
        )

        with st.spinner("Consultando rodadas..."):
            rodadas = carregar_rodadas(campeonato["id"])
        st.caption(
            f":material/update: Dados atualizados em {formatar_horario_atualizacao()}"
        )
        times = extrair_times(rodadas)

        if not times:
            st.warning("Nenhum time foi encontrado nas rodadas deste campeonato.")
            return

        proxima_rodada = localizar_proxima_rodada(rodadas)
        partidas_futuras = [
            partida
            for partida in proxima_rodada.get("partidas", [])
            if partida.get("status") == "aguardando"
        ]
        partidas_futuras.sort(
            key=lambda partida: partida.get("data_hora_realizacao") or ""
        )

        aba_time, aba_comparacao, aba_radar = st.tabs(
            ("Análise de time", "Comparação pré-jogo", "Radar da rodada")
        )

        with aba_time:
            coluna_time, coluna_jogos, coluna_mando = st.columns(3)
            time = coluna_time.selectbox(
                "Time",
                times,
                format_func=lambda item: item["nome"],
                key="time_individual",
            )
            quantidade = coluna_jogos.selectbox(
                "Últimos jogos", (5, 10), key="jogos_individual"
            )
            mando = coluna_mando.selectbox(
                "Mando",
                ("todos", "mandante", "visitante"),
                key="mando_individual",
            )

            if st.button(
                "Analisar", type="primary", width="stretch"
            ):
                relatorio = analisar_forma_time(
                    rodadas,
                    time_id=time["id"],
                    quantidade=quantidade,
                    mando=mando,
                )
                mostrar_relatorio(relatorio)

        with aba_comparacao:
            st.success(
                f"Próxima rodada identificada: {proxima_rodada['numero']}ª rodada"
            )
            coluna_partida, coluna_amostra = st.columns((2, 1))
            partida = coluna_partida.selectbox(
                "Partida",
                partidas_futuras,
                format_func=lambda item: (
                    f"{item['time_mandante']['nome']} × "
                    f"{item['time_visitante']['nome']} · "
                    f"{item.get('data_realizacao') or 'data não informada'} "
                    f"{item.get('hora_realizacao') or ''}"
                ),
                key="partida_proxima_rodada",
            )
            amostra = coluna_amostra.selectbox(
                "Jogos por time", (5, 10), key="jogos_comparacao"
            )
            mandante = partida["time_mandante"]
            visitante = partida["time_visitante"]

            if st.button(
                "Comparar times",
                type="primary",
                width="stretch",
            ):
                st.session_state["mostrar_comparacao"] = True

            if st.session_state.get("mostrar_comparacao", False):
                comparacao = comparar_mandante_visitante(
                    rodadas,
                    mandante_id=mandante["id"],
                    visitante_id=visitante["id"],
                    quantidade=amostra,
                )
                coluna_mandante, coluna_visitante = st.columns(2)
                with coluna_mandante:
                    mostrar_resumo_time(mandante["nome"], comparacao["mandante"])
                with coluna_visitante:
                    mostrar_resumo_time(visitante["nome"], comparacao["visitante"])

                st.subheader("Indicadores combinados")
                resumo = comparacao["resumo_combinado"]
                coluna_1, coluna_2, coluna_3, coluna_4 = st.columns(4)
                coluna_1.metric("Média de gols totais", resumo["media_gols_totais"])
                coluna_2.metric("Over 1.5 · média", f"{resumo['over_1_5_percentual_medio']}%")
                coluna_3.metric("Over 2.5 · média", f"{resumo['over_2_5_percentual_medio']}%")
                coluna_4.metric("Ambas marcam · média", f"{resumo['ambas_marcam_percentual_medio']}%")
                st.caption(
                    "As médias combinadas resumem os dois históricos; não são "
                    "probabilidades calibradas para a partida."
                )
                mostrar_confrontos_diretos(
                    mandante["nome"],
                    visitante["nome"],
                    comparacao["confrontos_diretos"],
                )

                st.subheader("Simulador de odds 1X2")
                st.caption(
                    "Digite manualmente as odds decimais exibidas pela casa. "
                    "Nenhuma aposta será enviada."
                )
                coluna_1, coluna_2, coluna_3 = st.columns(3)
                odd_mandante = coluna_1.number_input(
                    f"Vitória · {mandante['nome']}",
                    min_value=1.01,
                    value=2.00,
                    step=0.01,
                    format="%.2f",
                )
                odd_empate = coluna_2.number_input(
                    "Empate",
                    min_value=1.01,
                    value=3.00,
                    step=0.01,
                    format="%.2f",
                )
                odd_visitante = coluna_3.number_input(
                    f"Vitória · {visitante['nome']}",
                    min_value=1.01,
                    value=4.00,
                    step=0.01,
                    format="%.2f",
                )
                mercado = analisar_mercado_1x2(
                    odd_mandante=odd_mandante,
                    odd_empate=odd_empate,
                    odd_visitante=odd_visitante,
                )
                coluna_1, coluna_2 = st.columns(2)
                coluna_1.metric(
                    "Soma das probabilidades implícitas",
                    f"{mercado['soma_probabilidades']}%",
                )
                coluna_2.metric(
                    "Margem teórica do mercado",
                    f"{mercado['margem_teorica']}%",
                )
                st.dataframe(
                    [
                        {
                            "Resultado": nome.capitalize(),
                            "Odd": mercado["odds"][nome],
                            "Implícita": mercado["probabilidades_implicitas"][nome],
                            "Normalizada": mercado["probabilidades_normalizadas"][nome],
                        }
                        for nome in ("mandante", "empate", "visitante")
                    ],
                    column_config={
                        "Implícita": st.column_config.NumberColumn(format="%.2f%%"),
                        "Normalizada": st.column_config.NumberColumn(format="%.2f%%"),
                    },
                    hide_index=True,
                    width="stretch",
                )
                st.warning(
                    "Probabilidade implícita não é previsão do nosso modelo. "
                    "Ela representa o preço informado pela casa."
                )

                mostrar_simulador_duas_vias(
                    titulo="Ambas as equipes marcam",
                    opcao_a="Sim",
                    opcao_b="Não",
                    chave="ambas_marcam",
                )

                linha_gols = st.selectbox(
                    "Linha de total de gols",
                    (1.5, 2.5, 3.5),
                    index=1,
                    key="linha_total_gols",
                )
                mostrar_simulador_duas_vias(
                    titulo=f"Total de gols · linha {linha_gols}",
                    opcao_a=f"Acima de {linha_gols}",
                    opcao_b=f"Abaixo de {linha_gols}",
                    chave=f"total_gols_{str(linha_gols).replace('.', '_')}",
                )

        with aba_radar:
            st.subheader(f"Radar da {proxima_rodada['numero']}ª rodada")
            st.caption(
                "Ranking baseado no histórico recente do mandante em casa e "
                "do visitante fora. A pontuação ajusta a frequência pela amostra."
            )
            amostra_radar = st.selectbox(
                "Jogos por time",
                (5, 10),
                key="jogos_radar",
            )
            sinais = gerar_radar_rodada(
                rodadas,
                partidas_futuras,
                quantidade=amostra_radar,
            )

            if not sinais:
                st.warning(
                    "Não há histórico de mandante e visitante suficiente para "
                    "montar o radar desta rodada."
                )
            else:
                st.dataframe(
                    sinais,
                    column_config={
                        "partida": st.column_config.TextColumn(
                            "Partida", pinned=True
                        ),
                        "data": st.column_config.TextColumn("Data"),
                        "mercado": st.column_config.TextColumn("Mercado"),
                        "frequencia_historica": st.column_config.ProgressColumn(
                            "Frequência histórica",
                            min_value=0,
                            max_value=100,
                            format="%.1f%%",
                        ),
                        "jogos_analisados": st.column_config.NumberColumn(
                            "Jogos analisados"
                        ),
                        "confianca": st.column_config.TextColumn("Confiança"),
                        "pontuacao": st.column_config.ProgressColumn(
                            "Pontuação ajustada",
                            min_value=0,
                            max_value=100,
                            format="%.1f",
                        ),
                    },
                    hide_index=True,
                    width="stretch",
                )
                st.warning(
                    "O radar não considera odds, desfalques ou escalações e não "
                    "representa garantia de resultado ou recomendação de aposta."
                )

        st.info(
            "Os percentuais descrevem jogos passados. Não são garantia de "
            "resultado futuro nem recomendação automática de aposta."
        )
    except (
        ConfigurationError,
        DadosFutebolError,
        SemPartidasEncerradasError,
        ProximaRodadaNaoEncontradaError,
        ValueError,
    ) as exc:
        st.error(str(exc))
