class PostgresDialect:
    name = "postgres"

    def __init__(self, dsn: str):
        self._dsn = dsn

    def connect(self, retries: int = 5, delay: float = 2.0):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "psycopg is required for DB_URL=postgresql://... "
                "(pip install -r requirements-postgres.txt)"
            ) from exc
        last_exc = None
        for attempt in range(retries):
            try:
                return psycopg.connect(self._dsn, row_factory=dict_row)
            except Exception as exc:
                last_exc = exc
                if attempt < retries - 1:
                    import time
                    time.sleep(delay)
        raise last_exc

    def translate(self, sql: str) -> str:
        return sql.replace("datetime('now')", "now()").replace("?", "%s")

    def insert_sql(self, sql: str) -> str:
        return sql + " RETURNING id"

    def executescript(self, conn, script: str):
        # Drop leading "--" comment lines before splitting so every statement
        # chunk handed to psycopg is executable on its own.
        lines = [line for line in script.splitlines() if not line.strip().startswith("--")]
        cleaned = "\n".join(lines)
        # Never wait forever for a table lock: a rolling deploy runs two tasks
        # against the same database, and a blocked DDL would hang startup.
        conn.execute("SET LOCAL lock_timeout = '10s'")
        for statement in cleaned.split(";"):
            if statement.strip():
                conn.execute(statement)
        conn.commit()

    def last_id(self, cursor):
        row = cursor.fetchone()
        return int(row["id"]) if row else None

    def drop_table_sql(self, table: str) -> str:
        return f"DROP TABLE IF EXISTS {table} CASCADE"

    def recover_schema(self, conn) -> None:
        """Repair pre-CASCADE event foreign keys without locking the tables.

        The schema script used to drop and re-add these keys on every start.
        ALTER TABLE takes an ACCESS EXCLUSIVE lock, so a second task (rolling
        deploy) blocked at startup until the first task released its lock. The
        keys are now only touched when they are missing or lack ON DELETE
        CASCADE, which is a catalog read on a healthy database.
        """
        tables = {
            row["relname"]
            for row in conn.execute(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'public' AND c.relkind = 'r'"
            ).fetchall()
        }
        for table, constraint in (
            ("labels", "labels_event_id_fkey"),
            ("escalation_pending", "escalation_pending_event_id_fkey"),
        ):
            if table not in tables:
                continue
            row = conn.execute(
                "SELECT pg_get_constraintdef(oid) AS definition FROM pg_constraint "
                "WHERE conrelid = to_regclass(%s) AND conname = %s",
                (table, constraint),
            ).fetchone()
            definition = ((row or {}).get("definition") or "").upper()
            if "ON DELETE CASCADE" in definition:
                continue
            conn.execute(f"DELETE FROM {table} WHERE event_id NOT IN (SELECT id FROM events)")
            conn.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {constraint}")
            conn.execute(
                f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
                "FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE"
            )
        conn.commit()