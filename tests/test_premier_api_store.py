from futebol_analytics.database.csv_store import FOOTBALL_DATA_API_ORIGIN, import_premier_api


class Result:
    def fetchone(self):
        return {'id': '00000000-0000-0000-0000-000000000001'}


class Connection:
    def __init__(self):
        self.calls = []

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return Result()


class Context:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, *_):
        return False


class Store:
    def __init__(self):
        self.connection = Connection()

    def _connection(self):
        return Context(self.connection)


def test_imports_only_finished_score_fields():
    store = Store()
    capture = {'provedor': 'football-data', 'competicao': 'PL', 'temporada_inicio': 2025,
               'jogos': [{'status': 'FINISHED', 'utcDate': '2025-08-15T19:00:00Z',
                          'homeTeam': {'name': 'Liverpool FC'}, 'awayTeam': {'name': 'AFC Bournemouth'},
                          'score': {'fullTime': {'home': 4, 'away': 2}}}]}
    result = import_premier_api(store, capture, '2025/2026')
    assert result['jogos'] == 1
    assert result['origem'] == FOOTBALL_DATA_API_ORIGIN
    insert_params = store.connection.calls[1][1]
    assert insert_params[2:4] == ('Liverpool FC', 'AFC Bournemouth')
