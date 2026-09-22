from backend.storage import make_dialect
from backend.storage.postgres import PostgresDialect
from backend.storage.sqlite import SqliteDialect


def test_make_dialect_picks_backend():
    assert make_dialect("sqlite:///accessbell.db").name == "sqlite"
    assert make_dialect("accessbell.db").name == "sqlite"
    assert make_dialect("postgresql://user:pw@host:5432/db").name == "postgres"
    assert make_dialect("postgres://user:pw@host:5432/db").name == "postgres"


def test_postgres_translates_sql():
    dialect = PostgresDialect("postgresql://x")
    assert dialect.translate("SELECT * FROM t WHERE a=?") == "SELECT * FROM t WHERE a=%s"
    assert dialect.translate("UPDATE t SET x=datetime('now')") == "UPDATE t SET x=now()"
    assert dialect.insert_sql("INSERT INTO t (a) VALUES (?)").endswith("RETURNING id")


def test_sqlite_is_passthrough():
    dialect = SqliteDialect(":memory:")
    assert dialect.translate("SELECT * FROM t WHERE a=?") == "SELECT * FROM t WHERE a=?"
    assert dialect.insert_sql("INSERT INTO t (a) VALUES (?)") == "INSERT INTO t (a) VALUES (?)"


def test_drop_table_syntax_per_dialect():
    assert SqliteDialect(":memory:").drop_table_sql("events") == "DROP TABLE IF EXISTS events"
    assert PostgresDialect("postgresql://x").drop_table_sql("events") == "DROP TABLE IF EXISTS events CASCADE"