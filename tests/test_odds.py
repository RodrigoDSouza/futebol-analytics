import pytest

from futebol_analytics.analysis.odds import (
    analisar_mercado_1x2,
    analisar_mercado_duas_vias,
)


def test_calcula_probabilidades_e_margem_do_mercado() -> None:
    resultado = analisar_mercado_1x2(
        odd_mandante=2.0,
        odd_empate=4.0,
        odd_visitante=4.0,
    )

    assert resultado["probabilidades_implicitas"] == {
        "mandante": 50.0,
        "empate": 25.0,
        "visitante": 25.0,
    }
    assert resultado["soma_probabilidades"] == 100.0
    assert resultado["margem_teorica"] == 0.0
    assert resultado["probabilidades_normalizadas"] == {
        "mandante": 50.0,
        "empate": 25.0,
        "visitante": 25.0,
    }


def test_identifica_margem_acima_de_cem_por_cento() -> None:
    resultado = analisar_mercado_1x2(
        odd_mandante=1.9,
        odd_empate=3.5,
        odd_visitante=4.2,
    )

    assert resultado["soma_probabilidades"] > 100
    assert resultado["margem_teorica"] > 0


@pytest.mark.parametrize("odd", [1.0, 0.0, -2.0])
def test_rejeita_odd_invalida(odd: float) -> None:
    with pytest.raises(ValueError, match="maior que 1.00"):
        analisar_mercado_1x2(
            odd_mandante=odd,
            odd_empate=3.0,
            odd_visitante=4.0,
        )


def test_calcula_mercado_de_duas_vias() -> None:
    resultado = analisar_mercado_duas_vias(
        nome_opcao_a="Sim",
        odd_opcao_a=2.0,
        nome_opcao_b="Não",
        odd_opcao_b=2.0,
    )

    assert resultado["probabilidades_implicitas"] == {"Sim": 50.0, "Não": 50.0}
    assert resultado["margem_teorica"] == 0.0
    assert resultado["probabilidades_normalizadas"] == {
        "Sim": 50.0,
        "Não": 50.0,
    }


def test_rejeita_opcoes_com_o_mesmo_nome() -> None:
    with pytest.raises(ValueError, match="nomes diferentes"):
        analisar_mercado_duas_vias(
            nome_opcao_a="Over",
            odd_opcao_a=1.9,
            nome_opcao_b="Over",
            odd_opcao_b=1.9,
        )
