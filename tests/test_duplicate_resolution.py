import datetime as dt
import sqlite3

from smb_finsight.db import (
    DatabaseConfig,
    get_duplicate_stats,
    init_database,
    list_duplicate_entries,
    resolve_duplicate,
)


def setup_test_db(tmp_path):
    db_path = tmp_path / "test.db"
    cfg = DatabaseConfig(engine="sqlite", path=db_path)
    init_database(cfg)
    return cfg


def insert_import_batch(conn) -> int:
    """
    Insert a minimal import_batch row and return its id.

    This is required because entries.import_batch_id and
    duplicate_entries.import_batch_id reference import_batches.id.
    """
    cur = conn.execute(
        """
        INSERT INTO import_batches (created_at, source_type, source_label)
        VALUES (?, ?, ?)
        """,
        (dt.datetime.now(dt.timezone.utc).isoformat(), "test", "test-batch"),
    )
    conn.commit()
    return cur.lastrowid


def insert_entry(conn, **kwargs):
    conn.execute(
        """
        INSERT INTO entries (date, code, description, amount_cents, import_batch_id)
        VALUES (:date, :code, :description, :amount_cents, :import_batch_id)
        """,
        kwargs,
    )
    conn.commit()


def insert_duplicate(conn, **kwargs):
    conn.execute(
        """
        INSERT INTO duplicate_entries (
            date, code, description, amount_cents,
            import_batch_id, imported_at,
            existing_entry_id, resolution_status,
            resolution_comment
        )
        VALUES (
            :date, :code, :description, :amount_cents,
            :import_batch_id, :imported_at,
            :existing_entry_id, :resolution_status,
            :resolution_comment
        )
        """,
        kwargs,
    )
    conn.commit()


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------


def test_duplicate_stats_initial(tmp_path):
    cfg = setup_test_db(tmp_path)
    stats = get_duplicate_stats(cfg)
    assert stats.pending == 0
    assert stats.kept == 0
    assert stats.discarded == 0


def test_duplicate_resolution_flow(tmp_path):
    cfg = setup_test_db(tmp_path)
    conn = sqlite3.connect(cfg.path)

    # 1) Insert an import batch (required by FK)
    batch_id = insert_import_batch(conn)

    # 2) Insert an existing entry
    cur = conn.execute(
        """
        INSERT INTO entries (date, code, description, amount_cents, import_batch_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("2025-01-10", "706000", "Consulting", 200_000, batch_id),
    )
    existing_id = cur.lastrowid
    conn.commit()

    # 3) Insert a pending duplicate referencing this existing entry
    conn.execute(
        """
        INSERT INTO duplicate_entries (
            date,
            code,
            description,
            amount_cents,
            import_batch_id,
            imported_at,
            existing_entry_id,
            resolution_status,
            resolution_comment
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2025-01-10",
            "706000",
            "Consulting",
            200_000,
            batch_id,
            dt.datetime.now(dt.timezone.utc).isoformat(),
            existing_id,
            "pending",
            None,
        ),
    )
    conn.commit()

    # 4) Ensure duplicate appears in list
    duplicates = list_duplicate_entries(
        cfg,
        status="pending",
        import_batch_id=None,
        start=None,
        end=None,
        limit=None,
        offset=0,
    )
    assert len(duplicates) == 1
    dup = duplicates[0]
    assert dup.existing_entry_id == existing_id
    assert dup.resolution_status == "pending"

    # 5) Resolve as kept → creates new entry
    updated = resolve_duplicate(
        cfg,
        dup.id,
        "keep",
        comment="valid",
        resolved_by="cli",
    )

    assert updated.resolution_status == "kept"
    assert updated.resolved_by == "cli"
    assert updated.resolution_comment == "valid"
    assert updated.resolution_at is not None

    # Check new entry exists (original + inserted from duplicate)
    rows = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    assert rows == 2

    # Stats
    stats = get_duplicate_stats(cfg)
    assert stats.kept == 1
    assert stats.pending == 0
    assert stats.discarded == 0


def test_duplicate_discard(tmp_path):
    cfg = setup_test_db(tmp_path)
    conn = sqlite3.connect(cfg.path)

    # Insert import batch
    batch_id = insert_import_batch(conn)

    # Insert a single pending duplicate (no existing_entry_id needed here)
    conn.execute(
        """
        INSERT INTO duplicate_entries (
            date,
            code,
            description,
            amount_cents,
            import_batch_id,
            imported_at,
            existing_entry_id,
            resolution_status,
            resolution_comment
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2025-02-01",
            "623000",
            "Travel",
            50_000,
            batch_id,
            dt.datetime.now(dt.timezone.utc).isoformat(),
            None,
            "pending",
            None,
        ),
    )
    conn.commit()

    # Resolve as discard
    duplicates = list_duplicate_entries(
        cfg,
        status="pending",
        import_batch_id=None,
        start=None,
        end=None,
        limit=None,
        offset=0,
    )
    assert len(duplicates) == 1
    dup = duplicates[0]

    updated = resolve_duplicate(
        cfg,
        dup.id,
        "discard",
        comment="duplicate",
        resolved_by="cli",
    )

    assert updated.resolution_status == "discarded"
    assert updated.resolution_comment == "duplicate"
    assert updated.resolved_by == "cli"

    stats = get_duplicate_stats(cfg)
    assert stats.discarded == 1
    assert stats.pending == 0
    assert stats.kept == 0
