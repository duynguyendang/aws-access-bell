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
        # Strip "--" comment lines first (a statement chunk may *start* with a
        # comment), then run each statement with autocommit so that explicit
        # BEGIN/COMMIT pairs inside the script never nest.
        lines = [line for line in script.splitlines() if not line.strip().startswith("--")]
        cleaned = "\n".join(lines)
        previous_isolation = conn.isolation_level
        conn.isolation_level = None
        try:
            for statement in cleaned.split(";"):
                if statement.strip():
                    conn.execute(statement)
        finally:
            conn.isolation_level = previous_isolation
        conn.commit()

    def last_id(self, cursor):
        return cursor.lastrowid

    def drop_table_sql(self, table: str) -> str:
        return f"DROP TABLE IF EXISTS {table}"

    def recover_schema(self, conn) -> None:
        def tables() -> set:
            return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

        for orphan in ("escalation_pending_legacy", "escalation_pending_fix"):
            if orphan not in tables():
                continue
            if "escalation_pending" not in tables():
                conn.execute(f"ALTER TABLE {orphan} RENAME TO escalation_pending")
                continue
            if "events" in tables():
                conn.execute(
                    "INSERT OR IGNORE INTO escalation_pending (event_id, fire_at, timeout_seconds, created_at) "
                    f"SELECT ep.event_id, ep.fire_at, ep.timeout_seconds, ep.created_at FROM {orphan} ep "
                    "WHERE ep.event_id IN (SELECT id FROM events)"
                )
            conn.execute(f"DROP TABLE {orphan}")