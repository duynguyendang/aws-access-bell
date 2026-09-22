import sqlite3


class SqliteDialect:
    name = "sqlite"

    def __init__(self, path: str):
        self._path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def translate(self, sql: str) -> str:
        return sql

    def insert_sql(self, sql: str) -> str:
        return sql

    def executescript(self, conn, script: str):
        conn.executescript(script)

    def last_id(self, cursor):
        return cursor.lastrowid

    def drop_table_sql(self, table: str) -> str:
        return f"DROP TABLE IF EXISTS {table}"