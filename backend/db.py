import json
import threading
from contextlib import contextmanager
from pathlib import Path

from .storage import make_dialect
from .util import parse_iso

SCHEMA_DIR = Path(__file__).resolve().parent


class _Sql:
    def __init__(self, conn, dialect):
        self._conn = conn
        self._dialect = dialect

    def execute(self, sql, params=()):
        return self._conn.execute(self._dialect.translate(sql), params)

    def executescript(self, script: str):
        return self._dialect.executescript(self._conn, script)

    def __getattr__(self, name):
        return getattr(self._conn, name)


class Database:
    def __init__(self, url: str):
        self._dialect = make_dialect(url)
        self._lock = threading.RLock()
        self._conn = None
        self._connect()

    def _connect(self):
        self._conn = self._dialect.connect()
        return self._conn

    @contextmanager
    def _write(self):
        with self._lock:
            if self._conn is None:
                self._connect()
            try:
                yield _Sql(self._conn, self._dialect)
            except Exception:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
                raise

    def _insert(self, sql: str, params: tuple):
        with self._write() as conn:
            cur = conn.execute(self._dialect.insert_sql(sql), params)
            self._conn.commit()
            return self._dialect.last_id(cur)

    def init_schema(self):
        script = (SCHEMA_DIR / f"schema.{self._dialect.name}.sql").read_text(encoding="utf-8")
        with self._write() as conn:
            conn.executescript(script)
            self._conn.commit()

    def close(self):
        with self._lock:
            if self._conn is not None:
                self._conn.commit()
                self._conn.close()
                self._conn = None

    def insert_event(self, source, device_id, kind, occurred_at, raw: dict, event_hash: str | None = None) -> int:
        return self._insert(
            "INSERT INTO events (source, device_id, kind, occurred_at, raw_json, event_hash) VALUES (?,?,?,?,?,?)",
            (source, device_id, kind, occurred_at, json.dumps(raw, ensure_ascii=False), event_hash),
        )

    def get_event(self, event_id: int) -> dict | None:
        with self._write() as conn:
            row = conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
            return dict(row) if row else None

    def get_event_by_hash(self, event_hash: str) -> dict | None:
        if not event_hash:
            return None
        with self._write() as conn:
            row = conn.execute("SELECT * FROM events WHERE event_hash=? LIMIT 1", (event_hash,)).fetchone()
            return dict(row) if row else None

    def recent_matching(self, device_id: str, kind: str, limit: int = 10) -> list[dict]:
        with self._write() as conn:
            rows = conn.execute(
                "SELECT id, kind, occurred_at FROM events WHERE device_id=? AND kind=? ORDER BY id DESC LIMIT ?",
                (device_id, kind, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def update_status(self, event_id: int, status: str):
        with self._write() as conn:
            conn.execute("UPDATE events SET status=? WHERE id=?", (status, event_id))
            self._conn.commit()

    def update_triage(self, event_id: int, triage: dict, status: str | None = None):
        payload = json.dumps(triage, ensure_ascii=False)
        with self._write() as conn:
            if status:
                conn.execute("UPDATE events SET triage_json=?, status=? WHERE id=?", (payload, status, event_id))
            else:
                conn.execute("UPDATE events SET triage_json=? WHERE id=?", (payload, event_id))
            self._conn.commit()

    def set_event_created_at(self, event_id: int, created_at: str):
        with self._write() as conn:
            conn.execute("UPDATE events SET created_at=? WHERE id=?", (created_at, event_id))
            self._conn.commit()

    def list_events(self, since: str | None = None, until: str | None = None, limit: int = 50) -> list[dict]:
        sql = "SELECT * FROM events"
        where = []
        params: list = []
        if since:
            where.append("occurred_at >= ?")
            params.append(since)
        if until:
            where.append("occurred_at <= ?")
            params.append(until)
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY occurred_at DESC LIMIT ?"
        params.append(limit)
        with self._write() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]

    def add_expected_context(self, kind, label, window_start, window_end, source: str = "alexa") -> int:
        return self._insert(
            "INSERT INTO expected_context (kind, label, window_start, window_end, source) VALUES (?,?,?,?,?)",
            (kind, label, window_start, window_end, source),
        )

    def list_active_expected_context(self, at: str) -> list[dict]:
        t = parse_iso(at)
        with self._write() as conn:
            rows = conn.execute("SELECT * FROM expected_context").fetchall()
        active = []
        for r in rows:
            r = dict(r)
            if parse_iso(r["window_start"]) <= t <= parse_iso(r["window_end"]):
                active.append(r)
        return active

    def list_expected_context(self, limit: int = 100) -> list[dict]:
        with self._write() as conn:
            rows = conn.execute(
                "SELECT * FROM expected_context ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def clear_expected_context(self, expected_id: int | None = None, label: str | None = None) -> int:
        if expected_id is None and not label:
            return 0
        with self._write() as conn:
            if expected_id is not None:
                cur = conn.execute("DELETE FROM expected_context WHERE id=?", (expected_id,))
            else:
                cur = conn.execute("DELETE FROM expected_context WHERE label=?", (label,))
            self._conn.commit()
            return cur.rowcount

    def add_label(self, event_id: int, pattern_key: str, label: str, source: str = "alexa") -> int:
        return self._insert(
            "INSERT INTO labels (event_id, pattern_key, label, source) VALUES (?,?,?,?)",
            (event_id, pattern_key, label, source),
        )

    def labels_for_event(self, event_id: int) -> list[dict]:
        with self._write() as conn:
            rows = conn.execute(
                "SELECT label, pattern_key, source, confirmed_at FROM labels WHERE event_id=? ORDER BY id",
                (event_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def labels_for_device(self, device_id: str) -> list[dict]:
        if not device_id:
            return []
        with self._write() as conn:
            rows = conn.execute(
                "SELECT l.label FROM labels l JOIN events e ON e.id = l.event_id "
                "WHERE e.device_id=? ORDER BY l.id DESC LIMIT 20",
                (device_id,),
            ).fetchall()
        seen: set[str] = set()
        out: list[dict] = []
        for row in rows:
            label = row["label"]
            if label not in seen:
                seen.add(label)
                out.append({"label": label})
        return out

    def log_share(self, brief_date: str, recipient: str, message: str) -> int:
        return self._insert(
            "INSERT INTO share_log (brief_date, recipient, message) VALUES (?,?,?)",
            (brief_date, recipient, message),
        )

    def list_shares(self, limit: int = 50) -> list[dict]:
        with self._write() as conn:
            rows = conn.execute("SELECT * FROM share_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_share(self, share_id: int) -> dict | None:
        with self._write() as conn:
            row = conn.execute("SELECT * FROM share_log WHERE id=?", (share_id,)).fetchone()
            return dict(row) if row else None

    def event_status_counts(self) -> dict:
        with self._write() as conn:
            rows = conn.execute("SELECT status, COUNT(*) AS n FROM events GROUP BY status").fetchall()
            return {r["status"]: r["n"] for r in rows}

    def escalation_status_counts(self) -> dict:
        with self._write() as conn:
            rows = conn.execute("SELECT status, COUNT(*) AS n FROM escalation_log GROUP BY status").fetchall()
            return {r["status"]: r["n"] for r in rows}

    def get_prefs(self) -> dict:
        with self._write() as conn:
            row = conn.execute("SELECT mode, language FROM access_prefs WHERE id=1").fetchone()
        return {"mode": row["mode"], "language": row["language"]} if row else {"mode": "both", "language": "en"}

    def set_prefs(self, mode: str, language: str):
        with self._write() as conn:
            conn.execute(
                "UPDATE access_prefs SET mode=?, language=?, updated_at=datetime('now') WHERE id=1",
                (mode, language),
            )
            self._conn.commit()

    def purge_older_than(self, ttl_days: int) -> int:
        with self._write() as conn:
            if self._dialect.name == "postgres":
                cur = conn.execute(
                    "DELETE FROM events WHERE created_at < now() - (%s)::interval",
                    (f"{int(ttl_days)} days",),
                )
            else:
                cur = conn.execute(
                    "DELETE FROM events WHERE created_at < datetime('now', ?)",
                    (f"-{int(ttl_days)} days",),
                )
            self._conn.commit()
            return cur.rowcount

    def add_escalation_contact(self, label: str, recipient: str, channel: str = "sms") -> int:
        return self._insert(
            "INSERT INTO escalation_contacts (label, recipient, channel) VALUES (?,?,?)",
            (label, recipient, channel),
        )

    def list_escalation_contacts(self, enabled_only: bool = True) -> list[dict]:
        sql = "SELECT * FROM escalation_contacts"
        if enabled_only:
            sql += " WHERE enabled=1"
        sql += " ORDER BY id"
        with self._write() as conn:
            return [dict(r) for r in conn.execute(sql).fetchall()]

    def revoke_escalation_contact(self, contact_id: int) -> bool:
        with self._write() as conn:
            cur = conn.execute(
                "UPDATE escalation_contacts SET enabled=0, revoked_at=datetime('now') WHERE id=? AND enabled=1",
                (contact_id,),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def get_escalation_policy(self) -> dict:
        with self._write() as conn:
            row = conn.execute(
                "SELECT enabled, timeout_seconds, min_urgency FROM escalation_policy WHERE id=1"
            ).fetchone()
        return {
            "enabled": bool(row["enabled"]),
            "timeout_seconds": row["timeout_seconds"],
            "min_urgency": row["min_urgency"],
        }

    def set_escalation_policy(self, enabled=None, timeout_seconds=None, min_urgency=None) -> dict:
        with self._write() as conn:
            row = conn.execute(
                "SELECT enabled, timeout_seconds, min_urgency FROM escalation_policy WHERE id=1"
            ).fetchone()
            new_enabled = row["enabled"] if enabled is None else int(bool(enabled))
            new_timeout = row["timeout_seconds"] if timeout_seconds is None else int(timeout_seconds)
            new_urgency = row["min_urgency"] if min_urgency is None else int(min_urgency)
            conn.execute(
                "UPDATE escalation_policy SET enabled=?, timeout_seconds=?, min_urgency=? WHERE id=1",
                (new_enabled, new_timeout, new_urgency),
            )
            self._conn.commit()
        return {"enabled": bool(new_enabled), "timeout_seconds": new_timeout, "min_urgency": new_urgency}

    def log_escalation(self, event_id: int, contact_id: int | None, recipient: str, message: str, status: str) -> int:
        return self._insert(
            "INSERT INTO escalation_log (event_id, contact_id, recipient, message, status) VALUES (?,?,?,?,?)",
            (event_id, contact_id, recipient, message, status),
        )

    def list_escalation_log(self, limit: int = 50) -> list[dict]:
        with self._write() as conn:
            rows = conn.execute("SELECT * FROM escalation_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def upsert_pending_escalation(self, event_id: int, fire_at: str, timeout_seconds: int):
        with self._write() as conn:
            conn.execute("DELETE FROM escalation_pending WHERE event_id=?", (event_id,))
            conn.execute(
                "INSERT INTO escalation_pending (event_id, fire_at, timeout_seconds) VALUES (?,?,?)",
                (event_id, fire_at, timeout_seconds),
            )
            self._conn.commit()

    def claim_pending_escalation(self, event_id: int) -> bool:
        with self._write() as conn:
            cur = conn.execute("DELETE FROM escalation_pending WHERE event_id=?", (event_id,))
            self._conn.commit()
            return cur.rowcount > 0

    def list_pending_escalations(self) -> list[dict]:
        with self._write() as conn:
            rows = conn.execute("SELECT * FROM escalation_pending ORDER BY event_id").fetchall()
            return [dict(r) for r in rows]