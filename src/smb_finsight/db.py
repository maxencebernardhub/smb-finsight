# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Database helpers for SMB FinSight.

This module is responsible for:

- managing the application database schema,
- importing accounting entries into the database (from normalized DataFrames),
- loading entries for a given reporting period,
- exposing typed dataclasses used by the rest of the application.

Design decisions
----------------
- The database is the *single source of truth* for accounting entries.
- For 0.3.0, only SQLite is supported.
- Amounts are stored in integer cents (amount_cents) to avoid floating issues.
- Every entry belongs to an import batch (import_batch_id is NOT NULL).
- Potential duplicate entries are stored in a dedicated table
  (`duplicate_entries`) with a `pending` resolution status.
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


def _create_schema_if_needed(conn: sqlite3.Connection) -> None:
    """
    Create tables and indexes if they do not exist yet.

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
            rows_inserted INTEGER NOT NULL DEFAULT 0
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
            imported_at     TEXT    NOT NULL,  -- ISO datetime in UTC

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
            resolution_comment  TEXT,

            FOREIGN KEY (import_batch_id)   REFERENCES import_batches(id),
            FOREIGN KEY (existing_entry_id) REFERENCES entries(id)
        );
        """
    )

    # Indexes for performance (keep it minimal for 0.3.0)
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
    source_type: Literal["csv", "manual", "api"] = "csv",
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
        Timestamp to associate with the import. If None, uses datetime.utcnow().

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
                        date, code, description, amount_cents,
                        import_batch_id, imported_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (
                        iso_date,
                        code,
                        description,
                        amount_cents,
                        batch_id,
                        imported_at_iso,
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
        cur.execute("SELECT 1 FROM entries LIMIT 1;")
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
