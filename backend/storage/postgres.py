class PostgresDialect:
    name = "postgres"

    def __init__(self, dsn: str):
        self._dsn = dsn

    def connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "psycopg is required for DB_URL=postgresql://... "
                "(pip install -r requirements-postgres.txt)"
            ) from exc
        return psycopg.connect(self._dsn, row_factory=dict_row)

    def translate(self, sql: str) -> str:
        return sql.replace("datetime('now')", "now()").replace("?", "%s")

    def insert_sql(self, sql: str) -> str:
        return sql + " RETURNING id"

    def executescript(self, conn, script: str):
        # Drop leading "--" comment lines before splitting so every statement
        # chunk handed to psycopg is executable on its own.
        lines = [line for line in script.splitlines() if not line.strip().startswith("--")]
        cleaned = "\n".join(lines)
        for statement in cleaned.split(";"):
            if statement.strip():
                conn.execute(statement)
        conn.commit()

    def last_id(self, cursor):
        row = cursor.fetchone()
        return int(row["id"]) if row else None

    def drop_table_sql(self, table: str) -> str:
        return f"DROP TABLE IF EXISTS {table} CASCADE"