"""Adaptador mínimo do protocolo SQL HTTPS oficial do Neon."""

from datetime import date, datetime
from decimal import Decimal
import json
import re
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import httpx


class NeonHttpError(Exception):
    """Falha segura ao consultar o endpoint SQL HTTPS."""


def _parameter(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime, UUID, Decimal)):
        return str(value)
    obj = getattr(value, "obj", None)
    if obj is not None:
        return json.dumps(obj, ensure_ascii=False)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _query(statement: str) -> str:
    index = 0

    def placeholder(_: re.Match) -> str:
        nonlocal index
        index += 1
        return f"${index}"

    return re.sub(r"%s", placeholder, statement)


def _value(value: Any, oid: int) -> Any:
    if value is None:
        return None
    if oid in (20, 21, 23):
        return int(value)
    if oid in (700, 701, 1700):
        return float(value)
    if oid == 16:
        return value is True or str(value).lower() == "true"
    if oid in (114, 3802):
        return json.loads(value) if isinstance(value, str) else value
    if oid == 1082:
        return date.fromisoformat(value)
    if oid in (1114, 1184):
        return datetime.fromisoformat(value.replace(" ", "T"))
    return value


class NeonHttpResult:
    def __init__(self, payload: dict[str, Any]) -> None:
        fields = payload.get("fields", [])
        self.description = [type("Column", (), {"name": field["name"]}) for field in fields]
        names = [field["name"] for field in fields]
        oids = [field["dataTypeID"] for field in fields]
        self._rows = [dict(zip(names, (_value(value, oid) for value, oid in zip(row, oids))))
                      for row in payload.get("rows", [])]

    def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class NeonHttpCursor:
    def __init__(self, connection: "NeonHttpConnection") -> None:
        self.connection = connection
        self.result = NeonHttpResult({})

    @property
    def description(self):
        return self.result.description

    def execute(self, statement: str, params=()) -> "NeonHttpCursor":
        self.result = self.connection.execute(statement, params)
        return self

    def executemany(self, statement: str, values) -> None:
        for params in values:
            self.connection.execute(statement, params)

    def fetchone(self):
        return self.result.fetchone()

    def fetchall(self):
        return self.result.fetchall()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class NeonHttpConnection:
    def __init__(self, database_url: str, *, timeout: float = 30) -> None:
        self.database_url = database_url
        hostname = urlsplit(database_url).hostname
        if not hostname or not hostname.endswith(".neon.tech"):
            raise ValueError("A conexão HTTPS exige um host Neon.")
        self.endpoint = f"https://api.{hostname.split('.', 1)[1]}/sql"
        self.timeout = timeout

    def execute(self, statement: str, params=()) -> NeonHttpResult:
        try:
            response = httpx.post(
                self.endpoint,
                headers={
                    "Neon-Connection-String": self.database_url,
                    "Neon-Raw-Text-Output": "true",
                    "Neon-Array-Mode": "true",
                },
                json={"query": _query(statement), "params": [_parameter(value) for value in params]},
                timeout=self.timeout,
            )
            response.raise_for_status()
            return NeonHttpResult(response.json())
        except (httpx.HTTPError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise NeonHttpError(type(error).__name__) from None

    def cursor(self) -> NeonHttpCursor:
        return NeonHttpCursor(self)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False
