from datetime import date, datetime, timezone

from futebol_analytics.database.neon_http import NeonHttpConnection, NeonHttpResult, _query


def test_converts_psycopg_placeholders():
    assert _query("SELECT * FROM jogos WHERE id=%s AND nome=%s") == (
        "SELECT * FROM jogos WHERE id=$1 AND nome=$2")


def test_decodes_common_postgres_types():
    result = NeonHttpResult({
        "fields": [
            {"name": "n", "dataTypeID": 23},
            {"name": "dia", "dataTypeID": 1082},
            {"name": "instante", "dataTypeID": 1184},
            {"name": "dados", "dataTypeID": 3802},
        ],
        "rows": [["7", "2026-09-16", "2026-09-16 12:00:00+00:00", '{"ok":true}']],
    }).fetchone()
    assert result == {
        "n": 7,
        "dia": date(2026, 9, 16),
        "instante": datetime(2026, 9, 16, 12, tzinfo=timezone.utc),
        "dados": {"ok": True},
    }


def test_derives_https_endpoint_from_pooled_host():
    connection = NeonHttpConnection(
        "postgresql://user:password@ep-name-pooler.sa-east-1.aws.neon.tech/database?sslmode=require")
    assert connection.endpoint == "https://api.sa-east-1.aws.neon.tech/sql"
