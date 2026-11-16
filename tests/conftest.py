from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import Connection, sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import DictRow, dict_row

from app.config import settings
from app.main import app


@pytest.fixture
def database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Each integration test owns a schema; application data is never cleared."""
    schema = "test_" + uuid4().hex
    with psycopg.connect(settings.database_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        url = make_conninfo(settings.database_url, options=f"-c search_path={schema}")
        try:
            with psycopg.connect(url, autocommit=True) as conn:
                for path in sorted(Path("db/init").glob("*.sql")):
                    conn.execute(path.read_text(encoding="utf-8"))
            monkeypatch.setattr(settings, "database_url", url)
            yield url
        finally:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def conn(database_url: str) -> Iterator[Connection[DictRow]]:
    with psycopg.connect(database_url, autocommit=True, row_factory=dict_row) as connection:
        yield connection


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    # Using TestClient as a context manager runs the app lifespan (opens the DB pool).
    with TestClient(app) as c:
        yield c
