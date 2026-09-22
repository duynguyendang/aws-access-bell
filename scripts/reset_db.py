"""Reset the local SQLite database files (dev only)."""

from pathlib import Path

for name in ("accessbell.db", "accessbell.db-wal", "accessbell.db-shm"):
    path = Path(name)
    if path.exists():
        path.unlink()
        print("removed", path)
print("done")