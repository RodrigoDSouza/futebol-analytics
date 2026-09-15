"""Registro local das entradas e previsões disponíveis em uma execução."""

import hashlib
import json
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone


def _encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n').encode('utf-8')


def save_plan_record(root: Path, captures: list[dict], histories: dict,
                     mappings: dict, report: dict) -> Path:
    """Cria um pacote novo; nunca substitui uma execução anterior."""
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder = root / f'{stamp}-{uuid4().hex}'
    folder.mkdir(parents=True, exist_ok=False)
    files = {
        'agenda.json': captures,
        'historicos.json': histories,
        'mapa_times.json': mappings,
        'previsoes.json': report,
    }
    hashes = {}
    for name, value in files.items():
        content = _encoded(value)
        with (folder / name).open('xb') as handle:
            handle.write(content)
        hashes[name] = hashlib.sha256(content).hexdigest()
    manifest = {
        'versao': 1,
        'registrado_em': datetime.now(timezone.utc).isoformat(),
        'data_planejamento': report['data'],
        'calculado_em': report['calculado_em'],
        'modelo': 'frequencia_por_mando_laplace_v1',
        'arquivos_sha256': hashes,
        'nota': 'Captura operacional feita nesta execução; não reconstrói versões históricas anteriores.',
    }
    with (folder / 'manifesto.json').open('xb') as handle:
        handle.write(_encoded(manifest))
    return folder
