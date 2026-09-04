"""Ranking de sinais estatisticos para as partidas da proxima rodada."""

from typing import Any

from futebol_analytics.analysis.matchup import comparar_mandante_visitante
from futebol_analytics.analysis.team_form import SemPartidasEncerradasError


MERCADOS = (
    ("Mais de 1,5 gols", "over_1_5_percentual_medio"),
    ("Mais de 2,5 gols", "over_2_5_percentual_medio"),
    ("Ambas marcam", "ambas_marcam_percentual_medio"),
)


def gerar_radar_rodada(
    rodadas: list[dict[str, Any]],
    partidas: list[dict[str, Any]],
    *,
    quantidade: int = 5,
) -> list[dict[str, Any]]:
    """Ordena mercados por frequencia historica e cobertura da amostra."""
    if quantidade <= 0:
        raise ValueError("quantidade deve ser um inteiro positivo.")

    sinais: list[dict[str, Any]] = []
    for partida in partidas:
        mandante = partida.get("time_mandante") or {}
        visitante = partida.get("time_visitante") or {}
        if not isinstance(mandante.get("id"), int) or not isinstance(
            visitante.get("id"), int
        ):
            continue

        try:
            comparacao = comparar_mandante_visitante(
                rodadas,
                mandante_id=mandante["id"],
                visitante_id=visitante["id"],
                quantidade=quantidade,
            )
        except SemPartidasEncerradasError:
            continue

        jogos_analisados = (
            comparacao["mandante"]["jogos_analisados"]
            + comparacao["visitante"]["jogos_analisados"]
        )
        cobertura = min(jogos_analisados / (quantidade * 2), 1)
        confianca = _classificar_confianca(cobertura)
        resumo = comparacao["resumo_combinado"]

        for mercado, chave_percentual in MERCADOS:
            frequencia = resumo[chave_percentual]
            sinais.append(
                {
                    "partida": (
                        f"{mandante.get('nome', 'Mandante')} x "
                        f"{visitante.get('nome', 'Visitante')}"
                    ),
                    "data": partida.get("data_realizacao") or "Nao informada",
                    "mercado": mercado,
                    "frequencia_historica": frequencia,
                    "jogos_analisados": jogos_analisados,
                    "confianca": confianca,
                    "pontuacao": round(frequencia * cobertura, 1),
                }
            )

    return sorted(
        sinais,
        key=lambda sinal: (
            sinal["pontuacao"],
            sinal["frequencia_historica"],
            sinal["jogos_analisados"],
        ),
        reverse=True,
    )


def _classificar_confianca(cobertura: float) -> str:
    if cobertura >= 1:
        return "Alta"
    if cobertura >= 0.6:
        return "Media"
    return "Baixa"
