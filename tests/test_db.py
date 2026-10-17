def test_expected_context_window_matching(db):
    db.add_expected_context("ding", "pharmacy", "2026-09-15T09:00:00Z", "2026-09-15T10:30:00Z")
    inside = db.list_active_expected_context("2026-09-15T09:55:00Z")
    assert len(inside) == 1 and inside[0]["label"] == "pharmacy"
    assert db.list_active_expected_context("2026-09-15T11:00:00Z") == []
    assert db.list_active_expected_context("2026-09-14T09:30:00Z") == []
    edge = db.list_active_expected_context("2026-09-15T09:00:00Z")
    assert len(edge) == 1


def test_list_and_clear_expected_context(db):
    first = db.add_expected_context("ding", "pharmacy", "2026-09-15T09:00:00Z", "2026-09-15T10:30:00Z")
    db.add_expected_context("ding", "package", "2026-09-15T14:00:00Z", "2026-09-15T16:00:00Z")
    assert len(db.list_expected_context()) == 2
    assert db.clear_expected_context(first) == 1
    assert [w["label"] for w in db.list_expected_context()] == ["package"]
    assert db.clear_expected_context(label="package") == 1
    assert db.list_expected_context() == []
    assert db.clear_expected_context() == 0


def test_share_log_read_back_and_counts(db):
    event_id = db.insert_event("mock", "d1", "ding", "2026-09-15T10:00:00Z", {})
    db.update_status(event_id, "enriched")
    share_id = db.log_share("2026-09-15", "nurse@example.com", "AccessBell daily brief")
    assert db.get_share(share_id)["recipient"] == "nurse@example.com"
    assert db.list_shares()[0]["id"] == share_id
    assert db.event_status_counts() == {"enriched": 1}
    assert db.escalation_status_counts() == {}


def test_purge_older_than_removes_stale_events(db):
    fresh_id = db.insert_event("mock", "d1", "ding", "2026-09-15T10:00:00Z", {})
    stale_id = db.insert_event("mock", "d1", "ding", "2026-08-01T10:00:00Z", {})
    db.set_event_created_at(stale_id, "2000-01-01 00:00:00")
    purged = db.purge_older_than(30)
    assert purged == 1
    assert db.get_event(stale_id) is None
    assert db.get_event(fresh_id) is not None


def test_recent_matching_for_debounce(db):
    db.insert_event("ring", "d1", "ding", "2026-09-15T10:00:00Z", {})
    db.insert_event("ring", "d2", "ding", "2026-09-15T10:00:01Z", {})
    db.insert_event("ring", "d1", "motion", "2026-09-15T10:00:02Z", {})
    rows = db.recent_matching("d1", "ding")
    assert len(rows) == 1
    assert db.recent_matching("missing", "ding") == []


def test_labels_and_prefs(db):
    event_id = db.insert_event("ring", "d1", "ding", "2026-09-15T10:00:00Z", {})
    db.add_label(event_id, "device:d1", "that was pharmacy", source="alexa")
    assert db.labels_for_event(event_id)[0]["label"] == "that was pharmacy"
    assert db.labels_for_device("d1")[0]["label"] == "that was pharmacy"
    assert db.labels_for_device("other") == []
    assert db.get_prefs() == {"mode": "both", "language": "en"}
    db.set_prefs("voice", "vi")
    assert db.get_prefs() == {"mode": "voice", "language": "vi"}


def test_update_triage_status(db):
    from backend.triage import Tier1Rules

    event_id = db.insert_event("ring", "d1", "ding", "2026-09-15T10:00:00Z", {})
    db.update_triage(event_id, Tier1Rules().classify("ding").model_dump(), status="tier1")
    event = db.get_event(event_id)
    assert event["status"] == "tier1"
    assert "Someone is at the door" in event["triage_json"]


def _pending_row(database, event_id):
    with database._write() as conn:
        row = conn.execute(
            "SELECT event_id, fire_at FROM escalation_pending WHERE event_id=?", (event_id,)
        ).fetchone()
    return dict(row) if row else None


def test_init_schema_recovers_crash_after_pending_rename(tmp_path):
    from backend.db import Database

    database = Database(f"sqlite:///{tmp_path / 'recover_a.db'}")
    database.init_schema()
    event_id = database.insert_event("mock", "d1", "ding", "2026-09-15T10:00:00Z", {})
    with database._write() as conn:
        conn.execute(
            "INSERT INTO escalation_pending (event_id, fire_at, timeout_seconds) VALUES (?,?,?)",
            (event_id, "2026-09-15T10:01:30Z", 90),
        )
        conn.execute("ALTER TABLE escalation_pending RENAME TO escalation_pending_legacy")
        database._conn.commit()
    database.init_schema()
    assert _pending_row(database, event_id)["fire_at"] == "2026-09-15T10:01:30Z"
    database.close()


def test_init_schema_recovers_orphaned_legacy_and_fix_tables(tmp_path):
    from backend.db import Database

    database = Database(f"sqlite:///{tmp_path / 'recover_b.db'}")
    database.init_schema()
    event_id = database.insert_event("mock", "d1", "ding", "2026-09-15T10:00:00Z", {})
    columns = "(event_id INTEGER PRIMARY KEY, fire_at TEXT NOT NULL, timeout_seconds INTEGER NOT NULL, created_at TEXT)"
    with database._write() as conn:
        conn.execute(
            "INSERT INTO escalation_pending (event_id, fire_at, timeout_seconds) VALUES (?,?,?)",
            (event_id, "2026-09-15T10:01:30Z", 90),
        )
        conn.execute("ALTER TABLE escalation_pending RENAME TO escalation_pending_legacy")
        conn.execute(f"CREATE TABLE escalation_pending {columns}")
        conn.execute(f"CREATE TABLE escalation_pending_fix {columns}")
        database._conn.commit()
    database.init_schema()
    assert _pending_row(database, event_id)["fire_at"] == "2026-09-15T10:01:30Z"
    with database._write() as conn:
        names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "escalation_pending_legacy" not in names
    assert "escalation_pending_fix" not in names
    database.close()
