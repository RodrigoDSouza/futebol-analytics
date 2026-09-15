import hashlib
import json
from datetime import datetime, timezone

from futebol_analytics.journal import save_plan_record


def test_record_preserves_inputs_and_predictions_after_source_changes(tmp_path):
    capture = [{'provedor': 'football-data', 'partidas': [{'id': 10}]}]
    histories = {'E0:2026/2027': {'arquivo': {'sha256': 'csv-version-a'},
                                  'partidas': [{'data': '2026-09-14', 'gols_mandante': 2}]}}
    report = {'data': '2026-09-15', 'calculado_em': datetime.now(timezone.utc).isoformat(),
              'jogos': [{'id_api': 10, 'analise': {'probabilidade': 0.6}}]}
    first = save_plan_record(tmp_path, capture, histories, {}, report)
    capture[0]['partidas'][0]['id'] = 11
    histories['E0:2026/2027']['partidas'][0]['gols_mandante'] = 3
    report['jogos'][0]['analise']['probabilidade'] = 0.7
    second = save_plan_record(tmp_path, capture, histories, {}, report)

    assert first != second
    assert json.loads((first / 'agenda.json').read_text(encoding='utf-8'))[0]['partidas'][0]['id'] == 10
    assert json.loads((first / 'historicos.json').read_text(encoding='utf-8'))['E0:2026/2027']['partidas'][0]['gols_mandante'] == 2
    assert json.loads((first / 'previsoes.json').read_text(encoding='utf-8'))['jogos'][0]['analise']['probabilidade'] == 0.6
    manifest = json.loads((first / 'manifesto.json').read_text(encoding='utf-8'))
    for filename, digest in manifest['arquivos_sha256'].items():
        assert hashlib.sha256((first / filename).read_bytes()).hexdigest() == digest
