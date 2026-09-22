import os

import pytest

from backend.db import Database

TABLES = (
    "escalation_log",
    "escalation_pending",
    "escalation_contacts",
    "escalation_policy",
    "access_prefs",
    "share_log",
    "labels",
    "expected_context",
    "events",
)


def _reset(database):
    with database._write() as conn:
        for table in TABLES:
            conn.execute(database._dialect.drop_table_sql(table))
        database._conn.commit()


@pytest.fixture(params=["sqlite", "postgres"])
def db(request, tmp_path):
    if request.param == "sqlite":
        database = Database(f"sqlite:///{tmp_path / 'test.db'}")
    else:
        dsn = os.environ.get("TEST_POSTGRES_DSN")
        if not dsn:
            pytest.skip("TEST_POSTGRES_DSN not set")
        database = Database(dsn)
        _reset(database)
    database.init_schema()
    yield database
    if request.param == "postgres":
        _reset(database)
    database.close()