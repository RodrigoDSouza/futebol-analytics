"""Cálculos educacionais para odds decimais."""


def analisar_mercado_1x2(
    *,
    odd_mandante: float,
    odd_empate: float,
    odd_visitante: float,
) -> dict[str, object]:
    """Calcula probabilidades implícitas e margem de um mercado 1X2."""
    odds = {
        "mandante": odd_mandante,
        "empate": odd_empate,
        "visitante": odd_visitante,
    }
    for nome, odd in odds.items():
        if odd <= 1:
            raise ValueError(f"A odd de {nome} deve ser maior que 1.00.")

    implicitas = {nome: 100 / odd for nome, odd in odds.items()}
    soma_implicitas = sum(implicitas.values())
    normalizadas = {
        nome: round(probabilidade / soma_implicitas * 100, 2)
        for nome, probabilidade in implicitas.items()
    }

    return {
        "odds": odds,
        "probabilidades_implicitas": {
            nome: round(probabilidade, 2)
            for nome, probabilidade in implicitas.items()
        },
        "soma_probabilidades": round(soma_implicitas, 2),
        "margem_teorica": round(soma_implicitas - 100, 2),
        "probabilidades_normalizadas": normalizadas,
    }


def analisar_mercado_duas_vias(
    *,
    nome_opcao_a: str,
    odd_opcao_a: float,
    nome_opcao_b: str,
    odd_opcao_b: float,
) -> dict[str, object]:
    """Analisa odds de um mercado com dois resultados mutuamente exclusivos."""
    if not nome_opcao_a.strip() or not nome_opcao_b.strip():
        raise ValueError("Os nomes das opções não podem ficar vazios.")
    if nome_opcao_a == nome_opcao_b:
        raise ValueError("As opções do mercado devem ter nomes diferentes.")

    odds = {
        nome_opcao_a: odd_opcao_a,
        nome_opcao_b: odd_opcao_b,
    }
    for nome, odd in odds.items():
        if odd <= 1:
            raise ValueError(f"A odd de {nome} deve ser maior que 1.00.")

    implicitas = {nome: 100 / odd for nome, odd in odds.items()}
    soma_implicitas = sum(implicitas.values())

    return {
        "odds": odds,
        "probabilidades_implicitas": {
            nome: round(probabilidade, 2)
            for nome, probabilidade in implicitas.items()
        },
        "soma_probabilidades": round(soma_implicitas, 2),
        "margem_teorica": round(soma_implicitas - 100, 2),
        "probabilidades_normalizadas": {
            nome: round(probabilidade / soma_implicitas * 100, 2)
            for nome, probabilidade in implicitas.items()
        },
    }


def comparar_frequencia_odd(frequencia: float, odd: float) -> dict[str, float]:
    """Compara??o descritiva; n?o transforma frequ?ncia em previs?o."""
    import math
    if not math.isfinite(frequencia) or not 0 <= frequencia <= 100:
        raise ValueError("Frequ?ncia deve estar entre 0 e 100.")
    if not math.isfinite(odd) or odd <= 1:
        raise ValueError("Odd deve ser finita e maior que 1.")
    equilibrio = 100 / odd
    return {"equilibrio_percentual": equilibrio,
            "diferenca_pontos_percentuais": frequencia - equilibrio}
