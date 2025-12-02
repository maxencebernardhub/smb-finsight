# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Database layer for SMB FinSight.

This module provides all low-level accessors and utilities for interacting
with the SQLite database used by the application. It is responsible for:

- Initializing and migrating the database schema.
- Managing import batches (CSV, manual, API sources).
- Inserting accounting entries in bulk during an import.
- Detecting and recording potential duplicate entries.
- Exposing CRUD operations on individual accounting entries.
- Supporting soft deletion, restoration, and metadata tracking.
- Providing advanced query utilities for searching and filtering entries.

The database is the single source of truth for accounting entries across all
views, statements, KPIs, and multi-period comparisons.

------------------------------------------------------------------------------
Schema Overview (as of version 0.4.5)
------------------------------------------------------------------------------

The database contains three main tables:

1) import_batches
   One row per import batch, representing the origin of a set of entries.

   Columns:
   - id             INTEGER PRIMARY KEY AUTOINCREMENT
   - created_at     TEXT    NOT NULL (ISO datetime, UTC)
   - source_type    TEXT    NOT NULL  -- "csv" | "manual" | "api"
   - source_label   TEXT    NOT NULL  -- file path, connector name, etc.
   - rows_inserted  INTEGER NOT NULL
   - notes          TEXT            -- optional human-readable notes

   Import batches are used to group entries logically and capture metadata
   about how they were created (file imports, manual entry batches, etc.).


2) entries
   Core table storing all accounting entries in the system.

   Columns:
   - id              INTEGER PRIMARY KEY AUTOINCREMENT
   - date            TEXT    NOT NULL  -- ISO date "YYYY-MM-DD"
   - code            TEXT    NOT NULL  -- account code (chart of accounts)
   - description     TEXT
   - amount_cents    INTEGER NOT NULL  -- signed integer amount in cents
   - import_batch_id INTEGER NOT NULL  -- foreign key to import_batches.id

   -- Mutation tracking (added in v0.4.0)
   - updated_at      TEXT              -- UTC timestamp of last modification
   - is_deleted      INTEGER NOT NULL DEFAULT 0
   - deleted_at      TEXT              -- UTC timestamp when soft-deleted
   - deleted_reason  TEXT              -- optional reason for deletion

   Soft deletion allows entries to be marked as removed without being
   physically deleted. Deleted entries are ignored by analytics and reporting
   but can be searched, reviewed, restored, or permanently purged.


3) duplicate_entries
   Records entries that were detected as duplicates during an import.

   Columns:
   - id                  INTEGER PRIMARY KEY AUTOINCREMENT
   - date                TEXT NOT NULL
   - code                TEXT NOT NULL
   - description         TEXT
   - amount_cents        INTEGER NOT NULL
   - import_batch_id     INTEGER NOT NULL     -- foreign key to import_batches.id
   - imported_at         TEXT NOT NULL        -- timestamp of the import batch
   - existing_entry_id   INTEGER              -- id of the entry considered duplicate
   - resolution_status   TEXT NOT NULL        -- "pending" | "kept" | "discarded"
   - resolution_at       TEXT                 -- UTC timestamp when the duplicate
                                                 was resolved
   - resolved_by         TEXT                 -- "cli" | "webui" | "system"
   - resolution_comment  TEXT                 -- optional human-readable explanation

   Duplicate detection is used to avoid inserting the same entry multiple times
   when importing CSV files or syncing with external systems.


------------------------------------------------------------------------------
Key Responsibilities
------------------------------------------------------------------------------

1) Schema creation & migration
   - On startup, this module ensures the schema exists and performs
     in-place migrations when older versions are detected.
   - The migration logic is idempotent and safe to run multiple times.
   - Migrations for the `duplicate_entries` table were extended in v0.4.5
     to introduce resolution metadata (resolution_at, resolved_by).

2) Import batches
   - The function `import_entries` inserts a new import batch and then loads
     all entries from a DataFrame into the `entries` table.
   - Import metadata (source type, label, timestamps) is stored centrally.

3) Bulk import with duplicate detection
   - During import, each row is checked for an existing matching entry.
   - Exact matches are recorded in `duplicate_entries` with
     resolution_status="pending" instead of being inserted into `entries`.
   - The duplicate table preserves all candidate rows and is the only place
     where duplicate candidates are stored.
   - Starting with v0.4.5, duplicate rows also carry resolution metadata
     (resolution_at, resolved_by, resolution_comment) that drive the
     duplicate resolution workflow.

4) CRUD operations (added in v0.4.0)
   - `insert_entry` inserts a single new entry.
   - `update_entry` performs partial updates with automatic updated_at
     handling.
   - `soft_delete_entry` marks an entry as deleted (is_deleted=1) and
     records deletion metadata.
   - `restore_entry` reactivates a deleted entry.
   - `get_entry_by_id` loads a fully enriched AccountingEntry, including
     metadata from both entries and import_batches.

5) Advanced search utilities
   - `search_entries` accepts an EntriesFilter and supports:
     * date ranges,
     * exact or prefix account code matches,
     * substring search in descriptions,
     * amount bounds,
     * filtering by import batch,
     * inclusion/exclusion of deleted entries,
     * pagination and sorting.

6) Data types & dataclasses
   - The module defines typed dataclasses for:
     * `AccountingEntry`   (enriched, JOINed view),
     * `NewEntry`          (for inserts),
     * `EntryUpdate`       (for partial edits),
     * `EntriesFilter`     (for search queries),
     * `ImportStats`       (for bulk import reporting),
     * `DuplicateEntry`    (low-level view of `duplicate_entries` rows),
     * `DuplicateStats`    (aggregated counts by resolution status).

7) Duplicate resolution workflow (low-level API, v0.4.5)
   - `get_duplicate_stats` returns global counts of duplicates by status
     ("pending", "kept", "discarded").
   - `list_duplicate_entries` lists raw DuplicateEntry objects with optional
     filters (status, import_batch_id, date range).
   - `resolve_duplicate` applies a decision ("keep" or "discard") to a
     duplicate candidate, updating resolution metadata and, for "keep",
     inserting the candidate into `entries` as a new AccountingEntry.

These structures and functions provide a clean, typed interface for
consumption by higher layers of the application such as the CLI or the
upcoming Web UI.

------------------------------------------------------------------------------
SQLite Notes
------------------------------------------------------------------------------

- All timestamps are stored as ISO-8601 text (UTC).
- Foreign key enforcement is explicitly enabled.
- Migrations involving column removal are performed safely by rebuilding the
  affected table (`entries`) and copying its content.
- The database file is portable across platforms and can be bundled with a
  packaged version of the application.

------------------------------------------------------------------------------
End of module description.
------------------------------------------------------------------------------
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

import pandas as pd

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DatabaseConfig:
    """
    Database configuration for SMB FinSight.

    Attributes
    ----------
    engine:
        Database engine identifier. For 0.3.0, only "sqlite" is supported.
    path:
        Path to the SQLite database file.
    """

    engine: str
    path: Path


@dataclass(frozen=True)
class ImportStats:
    """
    Summary of an import of accounting entries into the database.

    Attributes
    ----------
    batch_id:
        Identifier of the batch row in `import_batches`.
    rows_inserted:
        Number of rows inserted into `entries`.
    duplicates_detected:
        Number of rows stored in `duplicate_entries` as potential duplicates.
    """

    batch_id: int
    rows_inserted: int
    duplicates_detected: int


SourceType = Literal["csv", "manual", "api"]
"""
Type alias for the origin of an import batch.

Values
------
- "csv"   : imported from a CSV file.
- "manual": created manually from the UI or CLI.
- "api"   : imported from an external API or integration.
"""


@dataclass(frozen=True)
class AccountingEntry:
    """
    Enriched representation of an accounting entry.

    This dataclass is designed for higher-level services (CLI, Web UI) and
    combines information coming from both `entries` and `import_batches`:

    - Base entry fields (from `entries`):
      * id
      * date
      * code
      * description
      * amount
      * import_batch_id
      * updated_at
      * is_deleted
      * deleted_at
      * deleted_reason

    - Batch metadata (from `import_batches`):
      * source_type
      * created_at (import timestamp)

    All timestamps are stored in UTC in the database and converted back to
    timezone-aware `datetime` objects when materializing `AccountingEntry`.
    """

    id: int

    # Core accounting data
    date: date
    code: str
    description: str | None
    amount: float
    import_batch_id: int

    # Batch metadata (JOIN with import_batches)
    source_type: SourceType | None
    created_at: datetime | None

    # Tracking metadata
    updated_at: datetime | None
    is_deleted: bool
    deleted_at: datetime | None
    deleted_reason: str | None


@dataclass(frozen=True)
class NewEntry:
    """
    Data required to create a new accounting entry.

    Notes
    -----
    - Every entry must belong to an import batch. For manual entries, higher
      level services are responsible for creating (or reusing) a dedicated
      import batch with `source_type="manual"` and then passing its id here.
    """

    date: date
    code: str
    description: str | None
    amount: float
    import_batch_id: int


@dataclass(frozen=True)
class EntryUpdate:
    """
    Fields that can be updated on an existing accounting entry.

    Each attribute is optional. Only non-None values are applied during
    the update operation.

    This dataclass is intentionally limited to business fields. Deletion
    is handled by dedicated functions (`soft_delete_entry`, `restore_entry`)
    rather than overloading this type.
    """

    date: date | None = None
    code: str | None = None
    description: str | None = None
    amount: float | None = None


@dataclass(frozen=True)
class EntriesFilter:
    """
    Filters used to search accounting entries.

    The filters can be combined. Date bounds are inclusive.

    Attributes
    ----------
    start, end:
        Inclusive date bounds (`date` column).
    code_exact:
        Exact account code match (e.g. "706000").
    code_prefix:
        Prefix match on account code (e.g. "70" to match all "70*").
    description_contains:
        Case-insensitive substring search on the description.
    min_amount, max_amount:
        Bounds on the signed amount (in monetary units).
    import_batch_id:
        Restrict search to a specific import batch.
    include_deleted:
        If False (default), returns only active entries.
    deleted_only:
        If True, returns only deleted entries. Takes precedence over
        `include_deleted` when both are True.
    """

    start: date | None = None
    end: date | None = None

    code_exact: str | None = None
    code_prefix: str | None = None

    description_contains: str | None = None

    min_amount: float | None = None
    max_amount: float | None = None

    import_batch_id: int | None = None

    include_deleted: bool = False
    deleted_only: bool = False


DuplicateDecision = Literal["keep", "discard"]
ResolvedBy = Literal["cli", "webui", "system"]


@dataclass(frozen=True)
class DuplicateEntry:
    """
    Low-level representation of a potential duplicate accounting entry.

    This dataclass mirrors a row from the `duplicate_entries` table and uses
    high-level Python types (date, datetime, float) for convenience.
    """

    id: int
    date: date
    code: str
    description: str | None
    amount: float
    import_batch_id: int
    imported_at: datetime
    existing_entry_id: int | None
    resolution_status: str
    resolution_at: datetime | None
    resolved_by: str | None
    resolution_comment: str | None


@dataclass(frozen=True)
class DuplicateStats:
    """
    Aggregated counts of duplicate entries by resolution status.

    This is primarily intended for UI layers (CLI, Web UI) to display data
    quality indicators (pending duplicates, resolved duplicates, etc.).
    """

    pending: int
    kept: int
    discarded: int


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ensure_sqlite(cfg: DatabaseConfig) -> None:
    """Raise if the configuration does not refer to a supported engine."""
    if cfg.engine.lower() != "sqlite":
        msg = (
            f"Unsupported database engine: {cfg.engine!r}. "
            "Only 'sqlite' is supported for now."
        )
        raise ValueError(msg)


def _connect(cfg: DatabaseConfig) -> sqlite3.Connection:
    """
    Open a SQLite connection with foreign keys enabled.

    The caller is responsible for closing the connection.
    """
    _ensure_sqlite(cfg)
    conn = sqlite3.connect(cfg.path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _get_table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    """
    Return the set of column names for the given table.

    Parameters
    ----------
    conn:
        Open SQLite connection.
    table:
        Table name.

    Returns
    -------
    set[str]
        Set of column names for the table.
    """
    cur = conn.execute(f"PRAGMA table_info({table});")
    return {row[1] for row in cur.fetchall()}


def _migrate_schema_if_needed(conn: sqlite3.Connection) -> None:
    """
    Migrate the database schema to the 0.4.x layout (0.4.0 → 0.4.5) if required.

    This function is idempotent and safe to call multiple times. It performs
    lightweight migrations in-place when older schemas are detected:

    - import_batches:
        * add `notes` column if missing.

    - entries:
        * ensure soft-delete related columns (`updated_at`, `is_deleted`,
          `deleted_at`, `deleted_reason`) exist.
        * drop legacy `imported_at` column by rebuilding the table when needed.

    Notes
    -----
    - Foreign key enforcement is temporarily disabled while rebuilding the
      `entries` table to avoid constraint issues when renaming the table.
    - Existing data is preserved and new columns are initialized with sensible
      defaults (`is_deleted = 0`, others = NULL).
    """

    # --- import_batches: ensure 'notes' column exists --------------------------------
    batch_columns = _get_table_columns(conn, "import_batches")
    if "notes" not in batch_columns:
        conn.execute("ALTER TABLE import_batches ADD COLUMN notes TEXT;")

    # --- entries: ensure new soft-delete columns & drop legacy 'imported_at' --------
    entry_columns = _get_table_columns(conn, "entries")

    # If the entries table does not exist yet, there is nothing to migrate for
    # this table, but we still want to continue with other migrations (e.g.
    # duplicate_entries in v0.4.5).
    if not entry_columns:
        entry_columns = set()

    needs_rebuild = False

    # We want to remove 'imported_at' from entries in 0.4.0.
    if "imported_at" in entry_columns:
        needs_rebuild = True

    # We also require the new columns to be present.
    required_new_columns = {
        "updated_at",
        "is_deleted",
        "deleted_at",
        "deleted_reason",
    }
    if not required_new_columns.issubset(entry_columns):
        needs_rebuild = True

    if needs_rebuild:
        # Temporarily disable foreign key checks while rebuilding the table.
        conn.execute("PRAGMA foreign_keys = OFF;")
        try:
            # Rename the old table.
            conn.execute("ALTER TABLE entries RENAME TO entries_old;")

            # Create the new table with the desired schema.
            conn.execute(
                """
                CREATE TABLE entries (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    date            TEXT    NOT NULL,  -- ISO date 'YYYY-MM-DD'
                    code            TEXT    NOT NULL,
                    description     TEXT,
                    amount_cents    INTEGER NOT NULL,
                    import_batch_id INTEGER NOT NULL,
                    updated_at      TEXT,
                    is_deleted      INTEGER NOT NULL DEFAULT 0,
                    deleted_at      TEXT,
                    deleted_reason  TEXT,
                    FOREIGN KEY (import_batch_id) REFERENCES import_batches(id)
                );
                """
            )

            # Copy data from the old table into the new one.
            conn.execute(
                """
                INSERT INTO entries (
                    id,
                    date,
                    code,
                    description,
                    amount_cents,
                    import_batch_id,
                    updated_at,
                    is_deleted,
                    deleted_at,
                    deleted_reason
                )
                SELECT
                    id,
                    date,
                    code,
                    description,
                    amount_cents,
                    import_batch_id,
                    NULL        AS updated_at,
                    0           AS is_deleted,
                    NULL        AS deleted_at,
                    NULL        AS deleted_reason
                FROM entries_old;
                """
            )

            conn.execute("DROP TABLE entries_old;")
        finally:
            conn.execute("PRAGMA foreign_keys = ON;")

    # --- duplicate_entries: add resolution_at and resolved_by (v0.4.5) ----------
    duplicate_columns = _get_table_columns(conn, "duplicate_entries")
    if duplicate_columns and (
        "resolution_at" not in duplicate_columns
        or "resolved_by" not in duplicate_columns
    ):
        # We need to rebuild the table to introduce the new columns and keep
        # a clean column ordering.
        conn.execute("PRAGMA foreign_keys = OFF;")
        try:
            conn.execute(
                """
                CREATE TABLE duplicate_entries_new (
                    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    date                TEXT    NOT NULL,
                    code                TEXT    NOT NULL,
                    description         TEXT,
                    amount_cents        INTEGER NOT NULL,

                    import_batch_id     INTEGER NOT NULL,
                    imported_at         TEXT    NOT NULL,

                    existing_entry_id   INTEGER,

                    resolution_status   TEXT    NOT NULL DEFAULT 'pending',
                    resolution_at       TEXT,
                    resolved_by         TEXT,
                    resolution_comment  TEXT,

                    FOREIGN KEY (import_batch_id) REFERENCES import_batches(id),
                    FOREIGN KEY (existing_entry_id) REFERENCES entries(id)
                );
                """
            )

            # Copy existing data into the new table. Older databases do not have
            # resolution_at / resolved_by, so we simply let them default to NULL.
            conn.execute(
                """
                INSERT INTO duplicate_entries_new (
                    id, date, code, description, amount_cents,
                    import_batch_id, imported_at,
                    existing_entry_id,
                    resolution_status, resolution_comment
                )
                SELECT
                    id, date, code, description, amount_cents,
                    import_batch_id, imported_at,
                    existing_entry_id,
                    resolution_status, resolution_comment
                FROM duplicate_entries;
                """
            )

            conn.execute("DROP TABLE duplicate_entries;")
            conn.execute(
                "ALTER TABLE duplicate_entries_new RENAME TO duplicate_entries;"
            )
        finally:
            conn.execute("PRAGMA foreign_keys = ON;")


def _create_schema_if_needed(conn: sqlite3.Connection) -> None:
    """
    Create tables and indexes if they do not exist yet and migrate the schema.

    This function is idempotent and can be called multiple times safely.
    """

    # import_batches: one row per import context (CSV file, manual input, API, ...)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS import_batches (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at    TEXT    NOT NULL,
            source_type   TEXT    NOT NULL,
            source_label  TEXT    NOT NULL,
            rows_inserted INTEGER NOT NULL DEFAULT 0,
            notes         TEXT
        );
        """
    )

    # entries: main accounting entries table
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS entries (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            date            TEXT    NOT NULL,  -- ISO date 'YYYY-MM-DD'
            code            TEXT    NOT NULL,
            description     TEXT,
            amount_cents    INTEGER NOT NULL,
            import_batch_id INTEGER NOT NULL,
            updated_at      TEXT,
            is_deleted      INTEGER NOT NULL DEFAULT 0,
            deleted_at      TEXT,
            deleted_reason  TEXT,

            FOREIGN KEY (import_batch_id) REFERENCES import_batches(id)
        );
        """
    )

    # duplicate_entries: potential duplicates detected at import time
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS duplicate_entries (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            date                TEXT    NOT NULL,
            code                TEXT    NOT NULL,
            description         TEXT,
            amount_cents        INTEGER NOT NULL,

            import_batch_id     INTEGER NOT NULL,
            imported_at         TEXT    NOT NULL,

            existing_entry_id   INTEGER,

            resolution_status   TEXT    NOT NULL DEFAULT 'pending',
            -- 'pending' | 'kept' | 'discarded'
            resolution_at       TEXT,
            resolved_by         TEXT,
            resolution_comment  TEXT,

            FOREIGN KEY (import_batch_id) REFERENCES import_batches(id),
            FOREIGN KEY (existing_entry_id) REFERENCES entries(id)
        );
        """
    )

    # Apply schema migrations for existing databases (0.4.0 and onwards).
    _migrate_schema_if_needed(conn)

    # Indexes
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_entries_date
            ON entries(date);
        """
    )

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_duplicate_entries_status
            ON duplicate_entries(resolution_status);
        """
    )

    conn.commit()


def _ensure_dataframe_columns(df: pd.DataFrame) -> None:
    """Validate that the DataFrame contains the expected columns."""
    required = {"date", "code", "description", "amount"}
    missing = required.difference(df.columns)
    if missing:
        cols = ", ".join(sorted(missing))
        msg = f"DataFrame is missing required column(s): {cols}"
        raise ValueError(msg)


def _to_iso_date(value) -> str:
    """Convert a date-like value to ISO 'YYYY-MM-DD' string."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    # Let pandas / python try to parse
    return date.fromisoformat(str(value)).isoformat()


def _now_utc_iso() -> str:
    """Return the current UTC datetime as ISO string."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_database(cfg: DatabaseConfig) -> None:
    """
    Initialize the database schema if needed.

    - Creates the SQLite file if it does not exist.
    - Creates tables and indexes (import_batches, entries, duplicate_entries)
      if they are missing.
    - This function is idempotent: calling it multiple times is safe.

    Raises
    ------
    ValueError
        If cfg.engine is not supported.
    sqlite3.Error
        If schema creation fails.
    """
    cfg.path.parent.mkdir(parents=True, exist_ok=True)

    conn = _connect(cfg)
    try:
        _create_schema_if_needed(conn)
    finally:
        conn.close()


def import_entries(
    df: pd.DataFrame,
    cfg: DatabaseConfig,
    *,
    source_type: SourceType = "csv",
    source_label: str,
    imported_at: datetime | None = None,
) -> ImportStats:
    """
    Import a batch of accounting entries into the database.

    Parameters
    ----------
    df:
        Normalized accounting entries with columns:
        - date (datetime/date / ISO string)
        - code (str)
        - description (str)
        - amount (float, signed)

    cfg:
        Database configuration.

    source_type:
        Origin of the batch, e.g. "csv", "manual", "api".
        Stored in import_batches.source_type.

    source_label:
        Human-readable label for the batch, e.g. a filename or UI label.
        Stored in import_batches.source_label.

    imported_at:
        Timestamp to associate with the import. If None, uses the current
        UTC time. The value is stored in `import_batches.created_at` and in
        `duplicate_entries.imported_at` for potential duplicates.


    Behavior
    --------
    - Creates a new row in import_batches.
    - For each entry in df:
        * converts `amount` to integer cents (amount_cents = round(amount * 100)).
        * searches for an existing entry in `entries` with the same:
              date, code, amount_cents, description.
          - if none found → inserts into `entries`.
          - if at least one found → inserts into `duplicate_entries` with
            existing_entry_id pointing to the first matching entry.
    - Updates import_batches.rows_inserted with the count of rows inserted into
      `entries`.

    Returns
    -------
    ImportStats
        - batch_id
        - rows_inserted
        - duplicates_detected

    Raises
    ------
    ValueError
        If df does not contain required columns.
    sqlite3.Error
        If database operations fail.
    """
    _ensure_dataframe_columns(df)
    init_database(cfg)  # ensure schema exists

    if imported_at is None:
        imported_at_iso = _now_utc_iso()
    else:
        imported_at_iso = imported_at.isoformat(timespec="seconds")

    conn = _connect(cfg)
    try:
        cur = conn.cursor()

        # 1) Create import_batch row
        cur.execute(
            """
            INSERT INTO import_batches (
                created_at,
                source_type,
                source_label,
                rows_inserted
            )
            VALUES (?, ?, ?, 0);
            """,
            (imported_at_iso, source_type, source_label),
        )
        batch_id = cur.lastrowid

        rows_inserted = 0
        duplicates_detected = 0

        # 2) Process each row in the DataFrame
        for _, row in df.iterrows():
            iso_date = _to_iso_date(row["date"])
            code = str(row["code"])
            raw_description = row["description"]
            description = None if pd.isna(raw_description) else str(raw_description)
            amount = float(row["amount"])
            amount_cents = int(round(amount * 100))

            # Look for an existing entry with same date, code, description, amount_cents
            cur.execute(
                """
                SELECT id FROM entries
                WHERE date = ?
                  AND code = ?
                  AND amount_cents = ?
                  AND COALESCE(description, '') = COALESCE(?, '');
                """,
                (iso_date, code, amount_cents, description),
            )
            row_existing = cur.fetchone()

            if row_existing is None:
                # No existing entry -> insert into entries
                cur.execute(
                    """
                    INSERT INTO entries (
                        date,
                        code,
                        description,
                        amount_cents,
                        import_batch_id,
                        updated_at,
                        is_deleted,
                        deleted_at,
                        deleted_reason
                    )
                    VALUES (?, ?, ?, ?, ?, NULL, 0, NULL, NULL);
                    """,
                    (
                        iso_date,
                        code,
                        description,
                        amount_cents,
                        batch_id,
                    ),
                )
                rows_inserted += 1

            else:
                # Potential duplicate -> insert into duplicate_entries
                existing_entry_id = row_existing[0]
                cur.execute(
                    """
                    INSERT INTO duplicate_entries (
                        date, code, description, amount_cents,
                        import_batch_id, imported_at,
                        existing_entry_id,
                        resolution_status,
                        resolution_comment
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', NULL);
                    """,
                    (
                        iso_date,
                        code,
                        description,
                        amount_cents,
                        batch_id,
                        imported_at_iso,
                        existing_entry_id,
                    ),
                )
                duplicates_detected += 1

        # 3) Update rows_inserted in import_batches
        cur.execute(
            """
            UPDATE import_batches
               SET rows_inserted = ?
             WHERE id = ?;
            """,
            (rows_inserted, batch_id),
        )

        conn.commit()

        return ImportStats(
            batch_id=batch_id,
            rows_inserted=rows_inserted,
            duplicates_detected=duplicates_detected,
        )

    finally:
        conn.close()


def load_entries(
    cfg: DatabaseConfig,
    start: date,
    end: date,
) -> pd.DataFrame:
    """
    Load accounting entries from the database for a given period.

    The returned DataFrame is suitable for the existing engine pipeline.

    Parameters
    ----------
    cfg:
        Database configuration.

    start, end:
        Inclusive date bounds for the reporting period.

    Returns
    -------
    pandas.DataFrame
        A DataFrame with columns:
        - date (datetime64[ns])
        - code (str)
        - description (str)
        - amount (float, signed)

        'amount' is reconstructed from `amount_cents / 100.0`.

    Notes
    -----
    - If no entries are found, an empty DataFrame with the same columns
      is returned.
    - This function assumes the schema has been initialized by
      `init_database()`.
    """
    init_database(cfg)

    start_iso = start.isoformat()
    end_iso = end.isoformat()

    conn = _connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT date, code, description, amount_cents
              FROM entries
             WHERE date BETWEEN ? AND ?
               AND is_deleted = 0
             ORDER BY date, id;
            """,
            (start_iso, end_iso),
        )

        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame(columns=["date", "code", "description", "amount"])

    df = pd.DataFrame(rows, columns=["date", "code", "description", "amount_cents"])
    # Convert date string -> datetime64
    df["date"] = pd.to_datetime(df["date"], format="%Y-%m-%d")
    # Reconstruct amount from cents
    df["amount"] = df["amount_cents"].astype(float) / 100.0
    df = df.drop(columns=["amount_cents"])
    return df


def has_entries(cfg: DatabaseConfig) -> bool:
    """
    Return True if the database contains at least one entry in `entries`.

    Useful to warn the user when the dashboard is requested on an empty DB.
    """
    init_database(cfg)

    conn = _connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM entries WHERE is_deleted = 0 LIMIT 1;")
        return cur.fetchone() is not None
    finally:
        conn.close()


def list_import_batches(cfg: DatabaseConfig) -> pd.DataFrame:
    """
    Return the list of import batches stored in the database.

    Columns:
    - id
    - created_at
    - source_type
    - source_label
    - rows_inserted
    """
    init_database(cfg)

    conn = _connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, created_at, source_type, source_label, rows_inserted
              FROM import_batches
             ORDER BY id DESC;
            """
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame(
            columns=["id", "created_at", "source_type", "source_label", "rows_inserted"]
        )

    df = pd.DataFrame(
        rows,
        columns=["id", "created_at", "source_type", "source_label", "rows_inserted"],
    )
    df["created_at"] = pd.to_datetime(df["created_at"])
    return df


# ---------------------------------------------------------------------------
# CRUD and search helpers for entries
# ---------------------------------------------------------------------------


def _row_to_accounting_entry(row: tuple) -> AccountingEntry:
    """
    Convert a database row (as returned by cursor.fetchone / fetchall) into
    an AccountingEntry instance.

    Expected row layout:
      (id, date, code, description, amount_cents, import_batch_id,
       source_type, created_at, updated_at, is_deleted, deleted_at, deleted_reason)
    """
    (
        entry_id,
        date_str,
        code,
        description,
        amount_cents,
        import_batch_id,
        source_type,
        created_at_str,
        updated_at_str,
        is_deleted_int,
        deleted_at_str,
        deleted_reason,
    ) = row

    entry_date = date.fromisoformat(date_str)

    created_at = (
        datetime.fromisoformat(created_at_str) if created_at_str is not None else None
    )
    updated_at = (
        datetime.fromisoformat(updated_at_str) if updated_at_str is not None else None
    )
    deleted_at = (
        datetime.fromisoformat(deleted_at_str) if deleted_at_str is not None else None
    )

    is_deleted = bool(is_deleted_int)

    amount = float(amount_cents) / 100.0

    return AccountingEntry(
        id=entry_id,
        date=entry_date,
        code=code,
        description=description,
        amount=amount,
        import_batch_id=import_batch_id,
        source_type=source_type,
        created_at=created_at,
        updated_at=updated_at,
        is_deleted=is_deleted,
        deleted_at=deleted_at,
        deleted_reason=deleted_reason,
    )


def _row_to_duplicate_entry(row: tuple) -> DuplicateEntry:
    """
    Convert a database row into a DuplicateEntry instance.

    Expected row layout (in order):
      (id, date, code, description, amount_cents,
       import_batch_id, imported_at,
       existing_entry_id,
       resolution_status, resolution_at, resolved_by, resolution_comment)
    """
    (
        dup_id,
        date_str,
        code,
        description,
        amount_cents,
        import_batch_id,
        imported_at_str,
        existing_entry_id,
        resolution_status,
        resolution_at_str,
        resolved_by,
        resolution_comment,
    ) = row

    duplicate_date = date.fromisoformat(date_str)
    imported_at = datetime.fromisoformat(imported_at_str)

    resolution_at = (
        datetime.fromisoformat(resolution_at_str)
        if resolution_at_str is not None
        else None
    )

    amount = float(amount_cents) / 100.0

    return DuplicateEntry(
        id=dup_id,
        date=duplicate_date,
        code=code,
        description=description,
        amount=amount,
        import_batch_id=import_batch_id,
        imported_at=imported_at,
        existing_entry_id=existing_entry_id,
        resolution_status=resolution_status,
        resolution_at=resolution_at,
        resolved_by=resolved_by,
        resolution_comment=resolution_comment,
    )


def get_entry_by_id(cfg: DatabaseConfig, entry_id: int) -> AccountingEntry | None:
    """
    Load a single accounting entry by id, including batch metadata.

    Parameters
    ----------
    cfg:
        Database configuration.
    entry_id:
        Identifier of the entry in `entries.id`.

    Returns
    -------
    AccountingEntry | None
        The matching entry, or None if not found.
    """
    init_database(cfg)

    conn = _connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                e.id,
                e.date,
                e.code,
                e.description,
                e.amount_cents,
                e.import_batch_id,
                b.source_type,
                b.created_at,
                e.updated_at,
                e.is_deleted,
                e.deleted_at,
                e.deleted_reason
            FROM entries AS e
            JOIN import_batches AS b
              ON e.import_batch_id = b.id
           WHERE e.id = ?;
            """,
            (entry_id,),
        )
        row = cur.fetchone()
    finally:
        conn.close()

    if row is None:
        return None

    return _row_to_accounting_entry(row)


def insert_entry(cfg: DatabaseConfig, new_entry: NewEntry) -> AccountingEntry:
    """
    Insert a new accounting entry into the database.

    Notes
    -----
    - The `import_batch_id` must reference an existing row in `import_batches`.
      Higher-level services are responsible for creating manual batches when
      needed.
    """
    init_database(cfg)

    iso_date = new_entry.date.isoformat()
    amount_cents = int(round(new_entry.amount * 100))

    conn = _connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO entries (
                date,
                code,
                description,
                amount_cents,
                import_batch_id,
                updated_at,
                is_deleted,
                deleted_at,
                deleted_reason
            )
            VALUES (?, ?, ?, ?, ?, NULL, 0, NULL, NULL);
            """,
            (
                iso_date,
                new_entry.code,
                new_entry.description,
                amount_cents,
                new_entry.import_batch_id,
            ),
        )
        entry_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    result = get_entry_by_id(cfg, entry_id)
    if result is None:
        msg = f"Entry #{entry_id} was just inserted but could not be reloaded."
        raise RuntimeError(msg)
    return result


def update_entry(
    cfg: DatabaseConfig,
    entry_id: int,
    update: EntryUpdate,
) -> AccountingEntry:
    """
    Apply a partial update to an existing accounting entry.

    Parameters
    ----------
    cfg:
        Database configuration.
    entry_id:
        Identifier of the entry in `entries.id`.
    update:
        Fields to update. Only non-None attributes are applied.

    Returns
    -------
    AccountingEntry
        The updated entry.

    Raises
    ------
    ValueError
        If no fields are provided for update.
    """
    init_database(cfg)

    fields: list[str] = []
    params: list[object] = []

    if update.date is not None:
        fields.append("date = ?")
        params.append(update.date.isoformat())
    if update.code is not None:
        fields.append("code = ?")
        params.append(update.code)
    if update.description is not None:
        fields.append("description = ?")
        params.append(update.description)
    if update.amount is not None:
        amount_cents = int(round(update.amount * 100))
        fields.append("amount_cents = ?")
        params.append(amount_cents)

    if not fields:
        raise ValueError("No fields to update in EntryUpdate.")

    # Always update the updated_at timestamp
    updated_at_iso = _now_utc_iso()
    fields.append("updated_at = ?")
    params.append(updated_at_iso)

    params.append(entry_id)

    conn = _connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE entries
               SET {", ".join(fields)}
             WHERE id = ?;
            """,
            params,
        )
        conn.commit()
    finally:
        conn.close()

    result = get_entry_by_id(cfg, entry_id)
    if result is None:
        msg = f"Entry #{entry_id} was updated but could not be reloaded."
        raise RuntimeError(msg)
    return result


def soft_delete_entry(
    cfg: DatabaseConfig,
    entry_id: int,
    reason: str | None = None,
) -> AccountingEntry:
    """
    Soft-delete an entry by marking it as deleted.

    Parameters
    ----------
    cfg:
        Database configuration.
    entry_id:
        Identifier of the entry in `entries.id`.
    reason:
        Optional human-readable reason for the deletion. This is stored in
        `deleted_reason` and can later be displayed in an audit / recycle bin
        view.

    Returns
    -------
    AccountingEntry
        The deleted entry (after update).
    """
    init_database(cfg)

    deleted_at_iso = _now_utc_iso()

    conn = _connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE entries
               SET is_deleted    = 1,
                   deleted_at    = ?,
                   deleted_reason = ?,
                   updated_at    = ?
             WHERE id = ?;
            """,
            (deleted_at_iso, reason, deleted_at_iso, entry_id),
        )
        conn.commit()
    finally:
        conn.close()

    result = get_entry_by_id(cfg, entry_id)
    if result is None:
        msg = f"Entry #{entry_id} was soft-deleted but could not be reloaded."
        raise RuntimeError(msg)
    return result


def restore_entry(cfg: DatabaseConfig, entry_id: int) -> AccountingEntry:
    """
    Restore a soft-deleted entry by clearing the deletion flags.

    Parameters
    ----------
    cfg:
        Database configuration.
    entry_id:
        Identifier of the entry in `entries.id`.

    Returns
    -------
    AccountingEntry
        The restored entry.
    """
    init_database(cfg)

    updated_at_iso = _now_utc_iso()

    conn = _connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE entries
               SET is_deleted     = 0,
                   deleted_at     = NULL,
                   deleted_reason = NULL,
                   updated_at     = ?
             WHERE id = ?;
            """,
            (updated_at_iso, entry_id),
        )
        conn.commit()
    finally:
        conn.close()

    result = get_entry_by_id(cfg, entry_id)
    if result is None:
        msg = f"Entry #{entry_id} was restored but could not be reloaded."
        raise RuntimeError(msg)
    return result


def search_entries(
    cfg: DatabaseConfig,
    filters: EntriesFilter,
    *,
    limit: int | None = None,
    offset: int = 0,
    order_by: tuple[str, str] = ("date", "ASC"),
) -> pd.DataFrame:
    """
    Search accounting entries using the given filters.

    The returned DataFrame is intended for listing / UI use and includes
    both entry and batch metadata.

    Result columns
    --------------
    - id
    - date
    - code
    - description
    - amount
    - import_batch_id
    - source_type
    - created_at
    - updated_at
    - is_deleted
    - deleted_at
    - deleted_reason
    """
    init_database(cfg)

    where_clauses: list[str] = ["1 = 1"]
    params: list[object] = []

    if filters.start is not None:
        where_clauses.append("e.date >= ?")
        params.append(filters.start.isoformat())
    if filters.end is not None:
        where_clauses.append("e.date <= ?")
        params.append(filters.end.isoformat())

    if filters.code_exact is not None:
        where_clauses.append("e.code = ?")
        params.append(filters.code_exact)
    elif filters.code_prefix is not None:
        where_clauses.append("e.code LIKE ?")
        params.append(filters.code_prefix + "%")

    if filters.description_contains is not None:
        where_clauses.append("LOWER(e.description) LIKE ?")
        params.append(f"%{filters.description_contains.lower()}%")

    if filters.min_amount is not None:
        where_clauses.append("e.amount_cents >= ?")
        params.append(int(round(filters.min_amount * 100)))
    if filters.max_amount is not None:
        where_clauses.append("e.amount_cents <= ?")
        params.append(int(round(filters.max_amount * 100)))

    if filters.import_batch_id is not None:
        where_clauses.append("e.import_batch_id = ?")
        params.append(filters.import_batch_id)

    if filters.deleted_only:
        where_clauses.append("e.is_deleted = 1")
    elif not filters.include_deleted:
        where_clauses.append("e.is_deleted = 0")

    # Validate and build ORDER BY clause
    allowed_order_columns = {"date", "code", "amount", "id"}
    order_column, order_direction = order_by
    if order_column not in allowed_order_columns:
        raise ValueError(f"Invalid order_by column: {order_column!r}")
    order_direction_upper = order_direction.upper()
    if order_direction_upper not in {"ASC", "DESC"}:
        raise ValueError(f"Invalid order_by direction: {order_direction!r}")

    if order_column == "amount":
        order_expr = "e.amount_cents"
    else:
        order_expr = f"e.{order_column}"

    order_clause = (
        f"ORDER BY {order_expr} {order_direction_upper}, e.id {order_direction_upper}"
    )

    limit_clause = ""
    if limit is not None:
        limit_clause = " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    query = f"""
        SELECT
            e.id,
            e.date,
            e.code,
            e.description,
            e.amount_cents,
            e.import_batch_id,
            b.source_type,
            b.created_at,
            e.updated_at,
            e.is_deleted,
            e.deleted_at,
            e.deleted_reason
        FROM entries AS e
        JOIN import_batches AS b
          ON e.import_batch_id = b.id
       WHERE {' AND '.join(where_clauses)}
       {order_clause}
       {limit_clause};
    """

    conn = _connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        return pd.DataFrame(
            columns=[
                "id",
                "date",
                "code",
                "description",
                "amount",
                "import_batch_id",
                "source_type",
                "created_at",
                "updated_at",
                "is_deleted",
                "deleted_at",
                "deleted_reason",
            ]
        )

    df = pd.DataFrame(
        rows,
        columns=[
            "id",
            "date",
            "code",
            "description",
            "amount_cents",
            "import_batch_id",
            "source_type",
            "created_at",
            "updated_at",
            "is_deleted",
            "deleted_at",
            "deleted_reason",
        ],
    )

    # Type conversions
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df["created_at"] = pd.to_datetime(df["created_at"])
    df["updated_at"] = pd.to_datetime(df["updated_at"], errors="coerce")
    df["deleted_at"] = pd.to_datetime(df["deleted_at"], errors="coerce")

    df["amount"] = df["amount_cents"].astype(float) / 100.0
    df = df.drop(columns=["amount_cents"])
    return df


# ---------------------------------------------------------------------------
# Duplicate entries API
# ---------------------------------------------------------------------------


def get_duplicate_stats(cfg: DatabaseConfig) -> DuplicateStats:
    """
    Compute aggregated counts of duplicate entries by resolution status.

    Parameters
    ----------
    cfg:
        Database configuration.

    Returns
    -------
    DuplicateStats
        Object containing counts for "pending", "kept", and "discarded".
    """
    init_database(cfg)
    conn = _connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT resolution_status, COUNT(*)
              FROM duplicate_entries
             GROUP BY resolution_status;
            """
        )
        counts: dict[str, int] = {status: count for status, count in cur.fetchall()}
    finally:
        conn.close()

    return DuplicateStats(
        pending=counts.get("pending", 0),
        kept=counts.get("kept", 0),
        discarded=counts.get("discarded", 0),
    )


def list_duplicate_entries(
    cfg: DatabaseConfig,
    *,
    status: str | None = None,
    import_batch_id: int | None = None,
    start: date | None = None,
    end: date | None = None,
    limit: int | None = 100,
    offset: int = 0,
) -> list[DuplicateEntry]:
    """
    List potential duplicate entries with optional filtering.

    This function returns raw DuplicateEntry objects and does not join with
    the `entries` table. Higher-level services can combine this with
    `get_entry_by_id` when they need the full existing AccountingEntry.

    Parameters
    ----------
    cfg:
        Database configuration.
    status:
        Optional resolution status filter ("pending", "kept", "discarded").
        If None, all statuses are included.
    import_batch_id:
        Optional filter to restrict duplicates to a specific import batch.
    start, end:
        Optional inclusive date bounds on the `date` column.
    limit, offset:
        Optional pagination settings. If limit is None, all rows are returned.

    Returns
    -------
    list[DuplicateEntry]
        List of duplicate entries matching the given filters.
    """
    init_database(cfg)

    where_clauses: list[str] = []
    params: list[object] = []

    if status is not None:
        where_clauses.append("resolution_status = ?")
        params.append(status)

    if import_batch_id is not None:
        where_clauses.append("import_batch_id = ?")
        params.append(import_batch_id)

    if start is not None:
        where_clauses.append("date >= ?")
        params.append(start.isoformat())

    if end is not None:
        where_clauses.append("date <= ?")
        params.append(end.isoformat())

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    limit_clause = ""
    if limit is not None:
        limit_clause = " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

    query = f"""
        SELECT
            id,
            date,
            code,
            description,
            amount_cents,
            import_batch_id,
            imported_at,
            existing_entry_id,
            resolution_status,
            resolution_at,
            resolved_by,
            resolution_comment
        FROM duplicate_entries
        {where_sql}
        ORDER BY date ASC, id ASC
        {limit_clause};
    """

    conn = _connect(cfg)
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
    finally:
        conn.close()

    return [_row_to_duplicate_entry(row) for row in rows]


def resolve_duplicate(
    cfg: DatabaseConfig,
    duplicate_id: int,
    decision: DuplicateDecision,
    *,
    comment: str | None = None,
    resolved_by: ResolvedBy = "cli",
) -> DuplicateEntry:
    """
    Resolve a single duplicate entry by either keeping or discarding it.

    When the decision is "keep", the candidate duplicate is inserted into
    the `entries` table as a new accounting entry. When the decision is
    "discard", the candidate is simply marked as discarded and never used
    in analytics.

    Parameters
    ----------
    cfg:
        Database configuration.
    duplicate_id:
        Identifier of the duplicate entry to resolve.
    decision:
        Either "keep" or "discard".
    comment:
        Optional human-readable explanation stored in resolution_comment.
    resolved_by:
        Origin of the resolution action ("cli", "webui", "system").

    Returns
    -------
    DuplicateEntry
        The updated DuplicateEntry after resolution.

    Raises
    ------
    ValueError
        If the duplicate does not exist or has already been resolved.
    """
    if decision not in ("keep", "discard"):
        msg = f"Unsupported duplicate resolution decision: {decision!r}"
        raise ValueError(msg)

    init_database(cfg)
    conn = _connect(cfg)
    try:
        cur = conn.cursor()

        # Load current duplicate state
        cur.execute(
            """
            SELECT
                id,
                date,
                code,
                description,
                amount_cents,
                import_batch_id,
                imported_at,
                existing_entry_id,
                resolution_status,
                resolution_at,
                resolved_by,
                resolution_comment
            FROM duplicate_entries
            WHERE id = ?;
            """,
            (duplicate_id,),
        )
        row = cur.fetchone()
        if row is None:
            raise ValueError(f"Duplicate entry with id {duplicate_id} does not exist.")

        duplicate = _row_to_duplicate_entry(row)
        if duplicate.resolution_status != "pending":
            raise ValueError(
                f"Duplicate entry {duplicate_id} has already been resolved "
                f"with status {duplicate.resolution_status!r}."
            )

        # If we keep the candidate, insert it into `entries` as a new row.
        if decision == "keep":
            amount_cents = int(round(duplicate.amount * 100))
            cur.execute(
                """
                INSERT INTO entries (
                    date,
                    code,
                    description,
                    amount_cents,
                    import_batch_id,
                    updated_at,
                    is_deleted,
                    deleted_at,
                    deleted_reason
                )
                VALUES (?, ?, ?, ?, ?, NULL, 0, NULL, NULL);
                """,
                (
                    duplicate.date.isoformat(),
                    duplicate.code,
                    duplicate.description,
                    amount_cents,
                    duplicate.import_batch_id,
                ),
            )

        # Map high-level decision ("keep"/"discard") to the persisted
        # resolution_status values used throughout the codebase and in
        # DuplicateStats ("kept"/"discarded").
        if decision == "keep":
            status_value = "kept"
        else:
            status_value = "discarded"

        # Update resolution metadata on the duplicate row.
        resolution_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        cur.execute(
            """
            UPDATE duplicate_entries
               SET resolution_status = ?,
                   resolution_at = ?,
                   resolved_by = ?,
                   resolution_comment = ?
             WHERE id = ?;
            """,
            (
                status_value,
                resolution_at,
                resolved_by,
                comment,
                duplicate_id,
            ),
        )

        conn.commit()

        # Reload and return the updated duplicate entry to reflect the new state.
        cur.execute(
            """
            SELECT
                id,
                date,
                code,
                description,
                amount_cents,
                import_batch_id,
                imported_at,
                existing_entry_id,
                resolution_status,
                resolution_at,
                resolved_by,
                resolution_comment
            FROM duplicate_entries
            WHERE id = ?;
            """,
            (duplicate_id,),
        )
        updated_row = cur.fetchone()
    finally:
        conn.close()

    if updated_row is None:
        # This should not happen but we guard against it for robustness.
        raise RuntimeError(
            f"Duplicate entry {duplicate_id} was updated but cannot be reloaded."
        )

    return _row_to_duplicate_entry(updated_row)
