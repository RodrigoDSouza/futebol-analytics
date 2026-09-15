"""Coleta antes de gravar: erros de rede nunca publicam uma captura parcial."""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from futebol_analytics.api.client import DadosFutebolClient
from futebol_analytics.api.exceptions import APIResponseError
from futebol_analytics.database.store import RESOURCES, SnapshotStore


def synchronize(client: DadosFutebolClient, store: SnapshotStore, resource: str,
                scope: str, source: str, *, max_pages: int = 100) -> UUID:
    if resource not in RESOURCES:
        raise ValueError("Recurso de sincronização inválido.")
    if type(max_pages) is not int or not 1 <= max_pages <= 1000:
        raise ValueError("max_pages deve estar entre 1 e 1000.")
    if resource == "campeonatos":
        if len(scope) != 4 or not scope.isascii() or not scope.isdigit():
            raise ValueError("A temporada deve ter quatro dígitos.")
    elif not scope.isascii() or not scope.isdigit() or int(scope) < 1:
        raise ValueError("O escopo deve ser um ID positivo retornado pela API.")
    else:
        scope = str(int(scope))
    started_at = datetime.now(timezone.utc)
    if resource in ("campeonatos", "partidas"):
        pages: list[dict[str, Any]] = []
        expected_last = None
        expected_total = None
        seen_ids: set[int] = set()
        for number in range(1, max_pages + 1):
            if resource == "campeonatos":
                page = client.listar_campeonatos(temporada=scope, pagina=number, por_pagina=100)
            else:
                page = client.listar_partidas(int(scope), pagina=number, por_pagina=100)
            meta = page["meta"]
            last = meta.get("ultima_pagina", 1)
            total = meta.get("total")
            if type(total) is not int or total < 0:
                raise APIResponseError("Total da paginação ausente ou inválido; captura não gravada.")
            if expected_last is not None and (last != expected_last or total != expected_total):
                raise APIResponseError("A paginação mudou durante a coleta; execute novamente.")
            expected_last, expected_total = last, total
            if last > max_pages:
                raise APIResponseError("Coleta excede o limite de páginas; captura não gravada.")
            for item in page["data"]:
                item_id = item.get("id")
                if type(item_id) is not int or item_id < 1 or item_id in seen_ids:
                    raise APIResponseError("ID ausente, inválido ou duplicado entre páginas; captura não gravada.")
                seen_ids.add(item_id)
            pages.append(page)
            if number == last:
                break
        else:
            raise APIResponseError("Coleta incompleta; captura não gravada.")
        if len(seen_ids) != expected_total:
            raise APIResponseError("Quantidade coletada difere do total informado; captura não gravada.")
        # Preserva inclusive os metadados de cada página retornada pelo provedor.
        payload = {"paginas": pages}
    elif resource in ("rodadas", "artilharia"):
        if resource == "rodadas":
            payload = client.consultar_rodadas(int(scope))
        else:
            payload = client.consultar_artilharia(int(scope))
        data, meta = payload["data"], payload.get("meta")
        if (not isinstance(data, list) or not all(isinstance(item, dict) for item in data)
                or not isinstance(meta, dict) or type(meta.get("total")) is not int
                or meta["total"] != len(data)
                or ("campeonato_id" in meta and meta["campeonato_id"] != int(scope))):
            raise APIResponseError("Lista incompleta ou incompatível com o campeonato; captura não gravada.")
        if resource == "rodadas" and any(not isinstance(item.get("partidas"), list) for item in data):
            raise APIResponseError("Rodadas sem estrutura de partidas; captura não gravada.")
    elif resource == "tabela":
        payload = client.consultar_tabela(int(scope))
        data = payload["data"]
        if (not isinstance(data, dict) or data.get("campeonato_id") != int(scope)
                or not isinstance(data.get("classificacao"), list)):
            raise APIResponseError("Tabela incompatível com o campeonato; captura não gravada.")
    else:
        payload = client.consultar_estatisticas(int(scope))
        data = payload["data"]
        if (not isinstance(data, dict) or data.get("partida_id") != int(scope)
                or not isinstance(data.get("estatisticas"), dict)):
            raise APIResponseError("Estatísticas incompatíveis com a partida; captura não gravada.")
    return store.save(resource, scope, source, payload, started_at, datetime.now(timezone.utc))
