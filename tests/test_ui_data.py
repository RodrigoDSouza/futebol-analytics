"""Testes das funcoes auxiliares da interface."""

from datetime import datetime, timezone

from futebol_analytics.ui.data import formatar_horario_atualizacao


def test_formata_horario_no_fuso_de_sao_paulo() -> None:
    instante_utc = datetime(2026, 9, 4, 19, 30, 45, tzinfo=timezone.utc)

    resultado = formatar_horario_atualizacao(instante_utc)

    assert resultado == "04/09/2026 às 16:30:45"
