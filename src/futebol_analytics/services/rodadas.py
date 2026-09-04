"""Casos de uso relacionados ao calendário de rodadas."""

from datetime import datetime
from typing import Any


class ProximaRodadaNaoEncontradaError(LookupError):
    """Indica que não há rodada futura com data conhecida."""


def localizar_proxima_rodada(
    rodadas: list[dict[str, Any]],
    *,
    agora: datetime | None = None,
) -> dict[str, Any]:
    """Localiza a rodada que contém a partida futura mais próxima."""
    momento_atual = agora or datetime.now().astimezone()
    candidatas: list[tuple[datetime, dict[str, Any]]] = []

    for rodada in rodadas:
        for partida in rodada.get("partidas", []):
            if partida.get("status") != "aguardando":
                continue

            data_partida = _converter_data(partida.get("data_hora_realizacao"))
            if data_partida is None:
                continue

            momento_comparavel = momento_atual
            if data_partida.tzinfo is None:
                momento_comparavel = momento_atual.replace(tzinfo=None)
            elif momento_atual.tzinfo is None:
                momento_comparavel = momento_atual.astimezone()

            if data_partida >= momento_comparavel:
                candidatas.append((data_partida, rodada))

    if not candidatas:
        raise ProximaRodadaNaoEncontradaError(
            "Nenhuma rodada futura com data conhecida foi encontrada."
        )

    return min(candidatas, key=lambda candidata: candidata[0])[1]


def _converter_data(valor: Any) -> datetime | None:
    if not isinstance(valor, str) or not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None

