from .postgres import PostgresDialect
from .sqlite import SqliteDialect


def make_dialect(url: str):
    if url.startswith(("postgres://", "postgresql://")):
        return PostgresDialect(url)
    path = url[len("sqlite:///") :] if url.startswith("sqlite:///") else url
    return SqliteDialect(path)


__all__ = ["make_dialect", "SqliteDialect", "PostgresDialect"]