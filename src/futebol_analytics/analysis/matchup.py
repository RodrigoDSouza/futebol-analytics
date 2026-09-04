"""Comparação pré-jogo baseada na forma recente dos participantes."""

from typing import Any

from futebol_analytics.analysis.team_form import analisar_forma_time
from futebol_analytics.analysis.head_to_head import analisar_confrontos_diretos


def comparar_mandante_visitante(
    rodadas: list[dict[str, Any]],
    *,
    mandante_id: int,
    visitante_id: int,
    quantidade: int = 5,
) -> dict[str, Any]:
    """Compara o mandante em casa com o visitante fora."""
    if mandante_id == visitante_id:
        raise ValueError("Mandante e visitante devem ser times diferentes.")

    mandante = analisar_forma_time(
        rodadas,
        time_id=mandante_id,
        quantidade=quantidade,
        mando="mandante",
    )
    visitante = analisar_forma_time(
        rodadas,
        time_id=visitante_id,
        quantidade=quantidade,
        mando="visitante",
    )

    return {
        "mandante": mandante,
        "visitante": visitante,
        "confrontos_diretos": analisar_confrontos_diretos(
            rodadas,
            time_a_id=mandante_id,
            time_b_id=visitante_id,
            quantidade=quantidade,
        ),
        "resumo_combinado": {
            "media_gols_totais": _media(
                mandante["media_gols_marcados"] + mandante["media_gols_sofridos"],
                visitante["media_gols_marcados"] + visitante["media_gols_sofridos"],
            ),
            "over_1_5_percentual_medio": _media(
                mandante["over_1_5"]["percentual"],
                visitante["over_1_5"]["percentual"],
            ),
            "over_2_5_percentual_medio": _media(
                mandante["over_2_5"]["percentual"],
                visitante["over_2_5"]["percentual"],
            ),
            "ambas_marcam_percentual_medio": _media(
                mandante["ambas_marcam"]["percentual"],
                visitante["ambas_marcam"]["percentual"],
            ),
        },
    }


def _media(valor_a: float, valor_b: float) -> float:
    return round((valor_a + valor_b) / 2, 1)
