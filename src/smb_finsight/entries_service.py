# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
High-level services for CRUD operations and accounting-entry reporting.

This module sits between:
- the low-level database helpers in `db.py`, and
- user-facing layers such as the CLI or a future Web UI (e.g. Streamlit).

It exposes a clean, typed interface for interacting with accounting entries
and for performing business-level reporting that requires combining:

- database entries,
- the active accounting standard,
- the chart of accounts (via accounts.py),
- period definitions (via periods.py).

Responsibilities
----------------
1) CRUD Operations
   - Create accounting entries (manual or imported).
   - Edit existing entries using partial updates.
   - Soft-delete entries with optional human-readable reasons.
   - Restore previously deleted entries.
   - Load individual entries (fully enriched with batch metadata).

2) Listing & Searching
   - List entries for any reporting period (FY, YTD, MTD, last month, etc.).
   - Apply domain filters using the EntriesFilter dataclass:
       * date ranges
       * account code (exact or prefix)
       * description substring matching
       * amount bounds
       * batch-based filtering
       * include/deleted-only flags
   - Pagination and ordering for UI integrations.

3) Unknown Accounts Reporting (added in version 0.4.0)
   - Load entries for a given period.
   - Load the chart of accounts for the active accounting standard.
   - Split entries into two categories:
       * known accounts (exact or prefix-matching)
       * unknown accounts (no matching prefix in the chart)
   - Produce a structured report:
       * known_entries: usable in statements and analytics
       * unknown_entries: entries that require mapping or correction
       * summary: count & total amount per unknown account code

   This enables higher-level layers (CLI or Web UI) to display:
   - validations for correctness of imported data,
   - diagnostics when chart of accounts definitions or mapping files
     are incomplete,
   - actionable lists of entries requiring manual review.

Design notes
------------
- CRUD functions do not validate account codes: the database is intentionally
  permissive and stores all imported rows exactly as they appear (raw journal).
  Business-level validation is performed only when explicitly requested
  (e.g. unknown accounts reporting).

- Higher-level validation (e.g. preventing invalid codes during manual entry
  in the Web UI) can build on top of these services.

- This module orchestrates the database layer, the chart of accounts utilities,
  and period utilities, but does not implement complex accounting or mapping
  rules itself. It remains lightweight and focused on orchestration.
"""

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from .accounts import (
    load_list_of_accounts,
    split_known_and_unknown_accounts,
    summarize_unknown_accounts,
)
from .config import AppConfig
from .db import (
    AccountingEntry,
    DatabaseConfig,
    DuplicateDecision,
    DuplicateEntry,
    DuplicateStats,
    EntriesFilter,
    EntryUpdate,
    NewEntry,
    ResolvedBy,
)
from .db import (
    get_duplicate_stats as _db_get_duplicate_stats,
)
from .db import (
    get_entry_by_id as _db_get_entry_by_id,
)
from .db import (
    insert_entry as _db_insert_entry,
)
from .db import (
    list_duplicate_entries as _db_list_duplicate_entries,
)
from .db import (
    resolve_duplicate as _db_resolve_duplicate,
)
from .db import (
    restore_entry as _db_restore_entry,
)
from .db import (
    search_entries as _db_search_entries,
)
from .db import (
    soft_delete_entry as _db_soft_delete_entry,
)
from .db import (
    update_entry as _db_update_entry,
)
from .periods import Period


@dataclass(frozen=True)
class DuplicatePair:
    """
    High-level view combining a duplicate candidate and its existing entry.

    The `duplicate` attribute contains the raw DuplicateEntry metadata stored
    in the `duplicate_entries` table. The `existing` attribute contains the
    AccountingEntry that was considered a duplicate match, or None if the
    original entry no longer exists.

    This structure is designed for UI layers (CLI, Web UI) that need to
    display side-by-side comparisons and drive the duplicate resolution
    workflow.
    """

    duplicate: DuplicateEntry
    existing: Optional[AccountingEntry]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_db_config(app_config: AppConfig) -> DatabaseConfig:
    """
    Convenience helper to access the database configuration from an AppConfig.

    Parameters
    ----------
    app_config:
        The global application configuration.

    Returns
    -------
    DatabaseConfig
        The database configuration to be used by low-level DB helpers.
    """
    return app_config.database


def _merge_filters(
    base: EntriesFilter,
    override: Optional[EntriesFilter],
) -> EntriesFilter:
    """
    Merge two EntriesFilter instances into a single one.

    The `base` filter is typically derived from a reporting period
    (start/end dates). The `override` filter usually comes from user input
    (UI or CLI) and can refine or extend the base filter.

    Rules
    -----
    - For scalar values (dates, strings, amounts), the override value is
      used when it is not None; otherwise the base value is kept.
    - For boolean flags (`include_deleted`, `deleted_only`), a logical OR
      is applied so that enabling a flag at any level keeps it enabled in
      the merged filter.
    """
    if override is None:
        return base

    return EntriesFilter(
        start=override.start or base.start,
        end=override.end or base.end,
        code_exact=override.code_exact or base.code_exact,
        code_prefix=override.code_prefix or base.code_prefix,
        description_contains=override.description_contains or base.description_contains,
        min_amount=override.min_amount
        if override.min_amount is not None
        else base.min_amount,
        max_amount=override.max_amount
        if override.max_amount is not None
        else base.max_amount,
        import_batch_id=override.import_batch_id or base.import_batch_id,
        include_deleted=base.include_deleted or override.include_deleted,
        deleted_only=base.deleted_only or override.deleted_only,
    )


# ---------------------------------------------------------------------------
# Listing and search
# ---------------------------------------------------------------------------


def list_entries_for_period(
    app_config: AppConfig,
    period: Period,
    extra_filters: Optional[EntriesFilter] = None,
    *,
    limit: Optional[int] = None,
    offset: int = 0,
    order_by: tuple[str, str] = ("date", "ASC"),
) -> pd.DataFrame:
    """
    List accounting entries for a given reporting period.

    Parameters
    ----------
    app_config:
        Global application configuration.
    period:
        Reporting period defining the [start, end] boundaries (inclusive).
    extra_filters:
        Optional additional filters (account code, description, amount
        bounds, import batch, deleted flags, etc.). These filters are
        merged with the period boundaries using `_merge_filters`.
    limit:
        Optional maximum number of rows to return (for pagination).
    offset:
        Optional offset for pagination, in number of rows.
    order_by:
        Sorting instructions as (column, direction). Supported columns:
        "date", "code", "amount", "id". Direction must be "ASC" or "DESC".

    Returns
    -------
    pandas.DataFrame
        A DataFrame including both entry and batch metadata, with columns:
        id, date, code, description, amount, import_batch_id, source_type,
        created_at, updated_at, is_deleted, deleted_at, deleted_reason.
    """
    base_filter = EntriesFilter(start=period.start, end=period.end)
    merged_filter = _merge_filters(base_filter, extra_filters)

    db_cfg = _get_db_config(app_config)
    df = _db_search_entries(
        db_cfg,
        merged_filter,
        limit=limit,
        offset=offset,
        order_by=order_by,
    )
    return df


def unknown_accounts_report_for_period(
    app_config: AppConfig,
    period: Period,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Build an "unknown accounts" report for a given reporting period.

    This helper:
    - loads all entries for the given period (excluding soft-deleted ones),
    - loads the chart of accounts from the standard-specific configuration,
    - splits entries into known and unknown accounts based on prefix-matching,
    - builds a summary of unknown accounts grouped by account code.

    Parameters
    ----------
    app_config:
        Global application configuration, used to:
        - access the database configuration,
        - locate the chart of accounts CSV via standard_config.
    period:
        Reporting period defining the [start, end] boundaries (inclusive).

    Returns
    -------
    (known_entries, unknown_entries, summary) : tuple of pandas.DataFrame
        - known_entries:
            Entries whose account code (or one of its prefixes) exists in
            the chart of accounts.
        - unknown_entries:
            Entries whose account code does not match any known prefix.
        - summary:
            Aggregated view of unknown entries, with columns:
                * code
                * entries_count
                * total_amount

    Raises
    ------
    ValueError
        If no chart_of_accounts file is configured for the current standard.
    """
    # 1) Load entries for the period (only non-deleted entries).
    entries_df = list_entries_for_period(
        app_config,
        period,
        extra_filters=None,
        limit=None,
        offset=0,
        order_by=("date", "ASC"),
    )

    if entries_df.empty:
        empty = pd.DataFrame(columns=entries_df.columns)
        empty_summary = pd.DataFrame(columns=["code", "entries_count", "total_amount"])
        return empty, empty.copy(), empty_summary

    # 2) Load chart of accounts from the standard configuration.
    std_cfg = app_config.standard_config
    if std_cfg.chart_of_accounts is None:
        msg = (
            "No chart_of_accounts file is configured for the current standard. "
            "Please set 'chart_of_accounts' in the standard-specific TOML file."
        )
        raise ValueError(msg)

    list_of_accounts = load_list_of_accounts(str(std_cfg.chart_of_accounts))
    known_codes = set(list_of_accounts["account_number"].astype(str).str.strip())

    # 3) Split entries into known and unknown accounts.
    known_entries, unknown_entries = split_known_and_unknown_accounts(
        entries_df,
        known_codes,
    )

    # 4) Build the summary for unknown entries.
    summary = summarize_unknown_accounts(unknown_entries)

    return known_entries, unknown_entries, summary


def search_entries(
    app_config: AppConfig,
    filters: EntriesFilter,
    *,
    limit: Optional[int] = None,
    offset: int = 0,
    order_by: tuple[str, str] = ("date", "ASC"),
) -> pd.DataFrame:
    """
    Search accounting entries using a generic EntriesFilter.

    This function is intended for use cases where the caller builds the
    complete filter (including date bounds if needed) rather than relying
    on a predefined reporting Period.

    Parameters
    ----------
    app_config:
        Global application configuration.
    filters:
        Filters to apply when searching entries.
    limit:
        Optional maximum number of rows to return (for pagination).
    offset:
        Optional offset for pagination, in number of rows.
    order_by:
        Sorting instructions as (column, direction). Supported columns:
        "date", "code", "amount", "id". Direction must be "ASC" or "DESC".

    Returns
    -------
    pandas.DataFrame
        DataFrame with the same columns as `list_entries_for_period`.
    """
    db_cfg = _get_db_config(app_config)
    return _db_search_entries(
        db_cfg,
        filters,
        limit=limit,
        offset=offset,
        order_by=order_by,
    )


# ---------------------------------------------------------------------------
# Duplicate resolution workflow
# ---------------------------------------------------------------------------


def get_duplicate_stats(app_config: AppConfig) -> DuplicateStats:
    """
    Retrieve global statistics about duplicate entries for the current app.

    This function is intended for high-level UI components such as:
    - a navigation bar badge showing how many duplicates are pending, or
    - a data quality dashboard summarizing resolved vs. unresolved duplicates.

    Parameters
    ----------
    app_config:
        Global application configuration.

    Returns
    -------
    DuplicateStats
        Aggregated counts for "pending", "kept", and "discarded" duplicates.
    """
    db_cfg = _get_db_config(app_config)
    return _db_get_duplicate_stats(db_cfg)


def list_duplicate_pairs(
    app_config: AppConfig,
    *,
    status: Optional[str] = "pending",
    import_batch_id: Optional[int] = None,
    period: Optional[Period] = None,
    limit: Optional[int] = 100,
    offset: int = 0,
) -> list[DuplicatePair]:
    """
    List duplicate entries along with their associated existing entries.

    This function is the main entry point for UI layers that need to display
    duplicates and allow the user to resolve them. It returns one DuplicatePair
    per duplicate candidate, combining:

    - DuplicateEntry: the candidate row stored in `duplicate_entries`, and
    - AccountingEntry (optional): the existing entry that was detected as a
      potential duplicate.

    Parameters
    ----------
    app_config:
        Global application configuration.
    status:
        Optional resolution status filter:
        - "pending": candidates waiting for a decision (default),
        - "kept": candidates that were inserted into `entries`,
        - "discarded": candidates that were explicitly discarded,
        - None: include all statuses.
    import_batch_id:
        Optional filter to restrict duplicates to a specific import batch.
    period:
        Optional reporting period used to constrain the candidate entry dates.
        When provided, the [start, end] bounds of the Period are mapped to the
        `date` column of the duplicate entries.
    limit, offset:
        Optional pagination settings. When limit is None, all matching
        duplicates are returned.

    Returns
    -------
    list[DuplicatePair]
        A list of high-level duplicate views ready to be consumed by the CLI
        or Web UI.
    """
    db_cfg = _get_db_config(app_config)

    start = period.start if period is not None else None
    end = period.end if period is not None else None

    duplicates = _db_list_duplicate_entries(
        db_cfg,
        status=status,
        import_batch_id=import_batch_id,
        start=start,
        end=end,
        limit=limit,
        offset=offset,
    )

    # Cache existing entries by id so that we do not re-load the same
    # AccountingEntry multiple times when several duplicates point to it.
    existing_cache: dict[int, AccountingEntry] = {}

    result: list[DuplicatePair] = []
    for duplicate in duplicates:
        existing: Optional[AccountingEntry]

        if duplicate.existing_entry_id is None:
            existing = None
        else:
            existing_id = duplicate.existing_entry_id
            if existing_id in existing_cache:
                existing = existing_cache[existing_id]
            else:
                existing = _db_get_entry_by_id(db_cfg, existing_id)
                if existing is not None:
                    existing_cache[existing_id] = existing

        result.append(
            DuplicatePair(
                duplicate=duplicate,
                existing=existing,
            )
        )

    return result


def resolve_duplicate_entry(
    app_config: AppConfig,
    duplicate_id: int,
    decision: DuplicateDecision,
    *,
    comment: Optional[str] = None,
    resolved_by: ResolvedBy = "cli",
) -> DuplicatePair:
    """
    Resolve a single duplicate entry by either keeping or discarding it.

    This high-level function wraps the low-level database helper and returns
    a DuplicatePair that can immediately be used by UI layers to update their
    views (e.g. removing the resolved duplicate from a list).

    When the decision is "keep":
        - the candidate duplicate is inserted into the `entries` table as a
          new AccountingEntry; and
        - the corresponding row in `duplicate_entries` is marked with
          resolution_status="kept".

    When the decision is "discard":
        - the candidate is simply marked as discarded and will never be used
          in analytics or financial statements.

    Parameters
    ----------
    app_config:
        Global application configuration.
    duplicate_id:
        Identifier of the duplicate entry to resolve.
    decision:
        Either "keep" or "discard".
    comment:
        Optional human-readable explanation for the decision. This value is
        stored in `resolution_comment` and can be displayed in audit views.
    resolved_by:
        Origin of the resolution action. Typical values are:
        - "cli":    when resolution is triggered from the command-line,
        - "webui":  when resolution is triggered from the Web UI,
        - "system": for automated or batch decisions.

    Returns
    -------
    DuplicatePair
        The updated DuplicatePair after resolution. The `duplicate` field
        reflects the new resolution_status / metadata, and the `existing`
        field contains the current state of the existing AccountingEntry
        (if still present).

    Raises
    ------
    ValueError
        If the duplicate does not exist or has already been resolved.
    """
    db_cfg = _get_db_config(app_config)

    updated_duplicate = _db_resolve_duplicate(
        db_cfg,
        duplicate_id,
        decision,
        comment=comment,
        resolved_by=resolved_by,
    )

    existing: Optional[AccountingEntry]
    if updated_duplicate.existing_entry_id is None:
        existing = None
    else:
        existing = _db_get_entry_by_id(db_cfg, updated_duplicate.existing_entry_id)

    return DuplicatePair(
        duplicate=updated_duplicate,
        existing=existing,
    )


def load_entry(app_config: AppConfig, entry_id: int) -> Optional[AccountingEntry]:
    """
    Load a single accounting entry by id.

    Parameters
    ----------
    app_config:
        Global application configuration.
    entry_id:
        Identifier of the entry in `entries.id`.

    Returns
    -------
    AccountingEntry or None
        The matching entry, or None if it does not exist.
    """
    db_cfg = _get_db_config(app_config)
    return _db_get_entry_by_id(db_cfg, entry_id)


# ---------------------------------------------------------------------------
# Create / update / delete operations
# ---------------------------------------------------------------------------


def create_entry(
    app_config: AppConfig,
    new_entry: NewEntry,
) -> AccountingEntry:
    """
    Create a new accounting entry.

    Parameters
    ----------
    app_config:
        Global application configuration.
    new_entry:
        Data for the new entry. The `import_batch_id` must refer to an
        existing batch, including for manual entries.

    Returns
    -------
    AccountingEntry
        The newly created entry, including batch metadata.

    Notes
    -----
    - Future versions may add validation here (e.g. ensuring the account
      code exists in the chart of accounts associated with the current
      accounting standard).
    """
    db_cfg = _get_db_config(app_config)

    # TODO: validate account code and other business rules if needed.
    created = _db_insert_entry(db_cfg, new_entry)
    return created


def edit_entry(
    app_config: AppConfig,
    entry_id: int,
    update: EntryUpdate,
) -> AccountingEntry:
    """
    Edit an existing accounting entry using a partial update.

    Parameters
    ----------
    app_config:
        Global application configuration.
    entry_id:
        Identifier of the entry to update.
    update:
        Fields to update. Only non-None attributes will be changed.

    Returns
    -------
    AccountingEntry
        The updated entry.

    Raises
    ------
    ValueError
        If no fields are provided for update.
    """
    db_cfg = _get_db_config(app_config)

    # TODO: apply additional validation if needed (e.g. prevent editing
    #       entries belonging to closed fiscal periods).
    updated = _db_update_entry(db_cfg, entry_id, update)
    return updated


def delete_entry(
    app_config: AppConfig,
    entry_id: int,
    reason: Optional[str] = None,
) -> AccountingEntry:
    """
    Soft-delete an entry by marking it as deleted.

    Parameters
    ----------
    app_config:
        Global application configuration.
    entry_id:
        Identifier of the entry to delete.
    reason:
        Optional human-readable reason for the deletion. This value is
        stored in `deleted_reason` and can be displayed in a "recycle bin"
        view or used for audit purposes.

    Returns
    -------
    AccountingEntry
        The entry after it has been marked as deleted.
    """
    db_cfg = _get_db_config(app_config)
    deleted = _db_soft_delete_entry(db_cfg, entry_id, reason)
    return deleted


def restore_deleted_entry(
    app_config: AppConfig,
    entry_id: int,
) -> AccountingEntry:
    """
    Restore a previously soft-deleted entry.

    Parameters
    ----------
    app_config:
        Global application configuration.
    entry_id:
        Identifier of the entry to restore.

    Returns
    -------
    AccountingEntry
        The restored entry (with `is_deleted=False`).
    """
    db_cfg = _get_db_config(app_config)
    restored = _db_restore_entry(db_cfg, entry_id)
    return restored
