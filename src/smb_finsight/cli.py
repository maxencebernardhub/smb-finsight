# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Command-Line Interface (CLI) for SMB FinSight.

This module wires together the main building blocks of SMB FinSight:

- global configuration (fiscal year, database, display options),
- standard-specific configuration (mapping templates, ratios rules),
- accounting entries import & database access,
- aggregation engine (statements),
- ratios/KPIs engine,
- view helpers (detail levels and tabular rendering).

The CLI is intentionally thin: it does not implement accounting or
financial logic itself. Instead, it orchestrates the underlying modules
based on command-line arguments and configuration files.


High-level pipeline
-------------------

The CLI executes the following steps:

1) Load the main TOML configuration (smb_finsight_config.toml by default)
   using ``load_app_config()``. This provides:

   - fiscal year definition,
   - accounting standard name,
   - accounting entries path,
   - standard-specific configuration (StandardConfig),
   - optional balance sheet / HR inputs,
   - ratios options and display options.

2) Resolve paths with optional CLI overrides (accounting entries,
   mapping templates, chart of accounts), while keeping TOML config
   as the source of truth.

3) Load the user-maintained chart of accounts and build a set of known
   account codes, as well as a mapping from account code to label.

4) Read normalized accounting entries from CSV and determine the
   reporting period from CLI arguments and configuration. Filter
   entries that fall outside the period.

5) Aggregate amounts into statement rows using mapping templates:
   - primary statement (usually an income statement),
   - optional secondary statement (for example, SIG for FR PCG).

6) Optionally build canonical measures, compute derived measures and
   ratios/KPIs based on the configured ratios rules.

7) Convert statements and ratios into tabular views and render them
   as console tables and/or CSV files depending on the display mode.


Configuration and overrides
---------------------------

By default, the CLI reads the main configuration from a TOML file
named ``smb_finsight_config.toml`` in the current working directory.
You can override this path using:

    --config PATH

Within that file, the accounting standard points to a standard-specific
TOML configuration (e.g. ``config/standard_fr_pcg.toml``) which defines:

- primary statement mapping (income_statement),
- optional secondary statement mapping (secondary_mapping),
- optional chart of accounts file,
- ratios rules file(s),
- statement labels for display.

The following CLI arguments can override paths defined in the TOML
configuration without modifying the configuration files:

- ``--income-statement-mapping``:
    Override the primary statement mapping CSV path.
- ``--secondary-mapping``:
    Override the secondary statement mapping CSV path.
- ``--chart-of-accounts``:
    Override the chart of accounts CSV path.

These overrides only affect the current CLI run and leave the TOML
configuration unchanged.

Accounting entries are now always read from the application database.
To feed the database from a CSV file, use the ``--import`` argument of
the CLI. The CSV is normalized and stored in the database before the
dashboard is computed.



Scopes: what to render
----------------------

The ``--scope`` argument controls which parts of the pipeline should
be rendered:

- ``statements`` (default):
    Render the primary statement only.

- ``all_statements``:
    Render the primary statement and, if configured for the current
    accounting standard, the secondary statement.

- ``ratios``:
    Render ratios/KPIs only. Statements are not printed nor exported.

- ``all``:
    Render both statements (primary + optional secondary) and ratios.

If ratios are disabled in the main configuration (ratios.enabled = false),
scopes including ``ratios`` will skip ratio computation and inform the user.


Statement views: level of detail
--------------------------------

The ``--view`` argument defines the level of detail for statement views.

For the primary statement (typically the income statement), all views below
apply as described. For secondary statements (for example, SIG under FR PCG),
the ``complete`` view falls back to the detailed template view (no account-
level drill-down is performed).

Available views:

- ``simplified``:
    Keep rows with level <= 1 (very aggregated view).

- ``regular``:
    Keep rows with level <= 2 (standard level of detail).

- ``detailed`` (default):
    Keep all template levels (no additional filtering).

- ``complete``:
    Start from the detailed view and insert account-level lines under
    level-3 'acc' rows, using the user-maintained chart of accounts.

The semantics of levels are defined by the mapping templates for each
standard. The view helpers rely only on generic columns such as
``level``, ``id``, ``name``, ``type`` and ``amount`` and remain
agnostic of the underlying accounting standard.


Period selection
----------------

The CLI supports both predefined and custom reporting periods.

Predefined periods (``--period``):

- ``fy``:
    Full fiscal year (start_date → end_date from config).
- ``ytd``:
    Year-to-date, from fiscal year start_date to today or to the
    configured end_date, depending on the implementation of
    ``determine_period_from_args``.
- ``mtd``:
    Month-to-date, from the first day of the current month to today.
- ``last-month``:
    The full previous calendar month.
- ``last-fy``:
    The previous fiscal year.

Custom periods:

- ``--from-date YYYY-MM-DD``
- ``--to-date YYYY-MM-DD``

When both ``--from-date`` and ``--to-date`` are provided, they define
an explicit period. If only one of them is provided, the missing bound
is taken from the fiscal year definition in the configuration.

Priority rules (in simplified form):

1) If custom dates (``--from-date`` or ``--to-date``) are provided,
   they take precedence over ``--period``.
2) Otherwise, if ``--period`` is provided, the corresponding predefined
   period is used.
3) If neither is provided, the full fiscal year (from config) is used.

Multi-period support
--------------------
As of version 0.3.5, the SMB FinSight computation engine supports full
multi-period analytics through the unified function
``compute_all_multi_period()``. This function computes statements,
measures (canonical, extra and derived) and ratios for any number of
periods in a single pass.

However, the CLI intentionally remains *single-period only* in this
version. This preserves a predictable and focused command-line interface
meant for technical usage, scripting and CSV extraction. Multi-period
dashboards, charts and interactive analytics will be handled primarily
in the upcoming Web UI (v0.5.x).

Future versions of the CLI may introduce optional multi-period commands
if needed, but this is not part of the v0.3.5 scope.


Ratios and levels
-----------------

Ratios and derived measures are computed based on canonical measures
extracted from the aggregated statements and additional inputs from
configuration (e.g. balance sheet inputs, HR inputs, period_days).

The process is:

1) Extract canonical measures from the primary (and optional secondary)
   statements using the mapping templates and their canonical_measure
   tags.

2) Merge additional measures from config (balance sheet, HR, period).

3) Compute derived measures using the [measures.*] sections from the
   standard-specific ratios rules TOML file.

4) Optionally apply an additional custom ratios pack (if configured).

5) Compute ratios per level using [ratios.<level>.*] sections from
   the same rules file.

The ``--ratios-level`` argument allows overriding the default ratios
level defined in the main configuration (ratios.default_level). Typical
values are:

- ``basic``
- ``advanced``
- ``full``


Display modes and output
------------------------

Rendering is controlled by a combination of configuration and CLI flags.

The main configuration defines a default display mode:

- ``display.mode = "table" | "csv" | "both"``

It can be overridden via:

- ``--display-mode table|csv|both``

Semantics:

- ``table``:
    Render results to stdout only:
    - statements as text tables (pandas.DataFrame.to_string),
    - ratios as a text table.

- ``csv``:
    Write CSV files only, no console tables.

- ``both``:
    Do both console tables and CSV files.

When CSV output is enabled (``display.mode`` includes "csv"), the CLI
uses an output directory determined by:

- ``--output DIR``:
    If provided, CSV files are written into DIR.

- otherwise:
    ``data/output`` is used, and created if it does not exist.

For each type of result, a file is written with a timestamp-based name:

- primary statement:
    ``income_statement_YYYY-MM-DD-HH-MM-SS.csv``
- secondary statement (when applicable):
    ``secondary_statement_YYYY-MM-DD-HH-MM-SS.csv``
- ratios:
    ``ratios_YYYY-MM-DD-HH-MM-SS.csv``

The exact set of files generated depends on the chosen ``--scope`` and
on whether ratios are enabled for the current standard.


Standard-specific labels
------------------------

The standard-specific configuration may define human-readable labels
for statements in a [statements] section (for example, in
``config/standard_fr_pcg.toml``):

- ``primary_label``:
    Label for the primary statement (e.g. "Compte de résultat (FR PCG)").

- ``secondary_label``:
    Label for the secondary statement (e.g. "Soldes intermédiaires de "
    "gestion (SIG)").

These labels are used by the CLI when rendering console tables. If a
secondary statement is configured but no label is provided, a generic
label ("Secondary statement") is used.


Examples
--------

Examples assume the current directory contains ``smb_finsight_config.toml``
and the standard-specific configuration is correctly set up.

1) Show the primary statement for the full fiscal year as a table:

    python -m smb_finsight.cli --scope statements --view detailed --display-mode table

2) Show primary + secondary statements for year-to-date and write CSV files:

    python -m smb_finsight.cli --scope all_statements --period ytd --display-mode both

3) Compute and display ratios only, using advanced level:

    python -m smb_finsight.cli \\
        --scope ratios --ratios-level advanced --display-mode table

4) Render everything (statements + ratios) for the last fiscal year and
   export only CSV files to a custom directory:

    python -m smb_finsight.cli \\
        --scope all \\
        --period last-fy \\
        --display-mode csv \\
        --output reports/output_fy_last

======================================================================
Entries subcommands (CRUD) — added in version 0.4.0
======================================================================

Starting with v0.4.0, the CLI exposes a complete CRUD interface for
accounting entries stored in the SQLite database. This replaces the
need to manipulate entries via CSV files once imported, and forms the
foundation for the upcoming Streamlit Web UI (v0.5.x).

The ``entries`` command group provides:

- listing entries for a period,
- free-form search across the entire DB,
- soft deletion with reasons,
- restoration of deleted entries,
- reporting unknown account codes.

These commands operate *after* database initialization and optional
CSV imports.


entries list
------------

List accounting entries for a reporting period, using the same period
selection rules as the main pipeline:

    python -m smb_finsight.cli entries list --period ytd
    python -m smb_finsight.cli entries list --from-date 2025-01-01 --to-date 2025-03-31

Filters include:

- ``--code`` or ``--code-prefix``
- ``--description-contains``
- ``--min-amount`` / ``--max-amount``
- ``--batch-id``
- ``--include-deleted`` / ``--deleted-only``
- ``--limit`` / ``--offset``
- ``--order-by`` / ``--order-direction``


entries search
--------------

Search entries across the entire database without period constraints:

    python -m smb_finsight.cli entries search --code-prefix 70
    python -m smb_finsight.cli entries search --description-contains stripe

Optional date bounds:

- ``--from-date``
- ``--to-date``

This is ideal for developers, auditors, and debugging workflows.


entries delete
--------------

Soft-delete a single entry:

    python -m smb_finsight.cli entries delete 42 --reason "duplicate"

Soft deletes set:

- ``is_deleted = 1``
- ``deleted_at = UTC timestamp``
- ``deleted_reason = <user text>``


entries restore
---------------

Restore an entry that was previously soft-deleted:

    python -m smb_finsight.cli entries restore 42

This clears deletion fields and updates ``updated_at``.


entries unknown-accounts
------------------------

Report unknown account codes for a selected period, based on
prefix-matching against the chart of accounts:

    python -m smb_finsight.cli entries unknown-accounts --period fy
    python -m smb_finsight.cli entries unknown-accounts --show-entries

Returns:

- summary per unknown account code,
- optional detailed list of all unknown entries.

This is the main diagnostic tool for detecting unmapped or invalid
accounts after imports.



End of module description.
"""

import argparse
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from . import __version__
from .accounts import filter_unknown_accounts, load_list_of_accounts
from .config import load_app_config
from .db import EntriesFilter, has_entries, import_entries, init_database, load_entries
from .engine import aggregate, build_canonical_measures
from .entries_service import (
    delete_entry as service_delete_entry,
)
from .entries_service import (
    list_entries_for_period,
)
from .entries_service import (
    restore_deleted_entry as service_restore_entry,
)
from .entries_service import (
    search_entries as service_search_entries,
)
from .entries_service import (
    unknown_accounts_report_for_period as service_unknown_accounts_report,
)
from .io import read_accounting_entries
from .mapping import Template
from .periods import determine_period_from_args
from .ratios import compute_derived_measures, compute_ratios
from .views import (
    apply_view_level_filter,
    build_complete_view,
    ratios_to_dataframe,
)


def _build_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser for the CLI."""
    ap = argparse.ArgumentParser(
        prog="python -m smb_finsight.cli",
        description=(
            "SMB FinSight - Financial Dashboard & Analysis application for SMBs. "
            "Reads accounting entries, aggregates them using standard-specific "
            "mapping templates, computes ratios/KPIs and renders financial "
            "statements and ratios."
        ),
    )

    # Generic options
    ap.add_argument(
        "--version",
        action="store_true",
        help="Show the installed version of smb_finsight and exit.",
    )

    ap.add_argument(
        "--config",
        dest="config_path",
        help=(
            "Path to the main TOML configuration file. "
            "If omitted, 'smb_finsight_config.toml' in the current directory is used."
        ),
    )

    # Optional import: feed the database from a CSV file before running the dashboard
    ap.add_argument(
        "--import",
        dest="import_path",
        metavar="CSV_PATH",
        help=(
            "Import accounting entries from the given CSV file into the "
            "database before running the dashboard."
        ),
    )

    # Path overrides (optional, override TOML config for mappings and chart of accounts)
    ap.add_argument(
        "--income-statement-mapping",
        dest="income_statement_mapping",
        help=(
            "Override the primary income statement mapping CSV path defined in "
            "the standard-specific configuration."
        ),
    )

    ap.add_argument(
        "--secondary-mapping",
        dest="secondary_mapping",
        help=(
            "Override the secondary statement mapping CSV path defined in the "
            "standard-specific configuration."
        ),
    )

    ap.add_argument(
        "--chart-of-accounts",
        dest="chart_of_accounts",
        help=(
            "Override the chart of accounts CSV path defined in the "
            "standard-specific configuration."
        ),
    )

    # Period selection
    ap.add_argument(
        "--period",
        choices=["fy", "ytd", "mtd", "last-month", "last-fy"],
        help=(
            "Predefined reporting period. "
            "One of: fy, ytd, mtd, last-month, last-fy. "
            "If not provided, the full fiscal year from config is used."
        ),
    )
    ap.add_argument(
        "--from-date",
        dest="from_date",
        help=(
            "Custom period start date (YYYY-MM-DD). If provided without "
            "--to-date, the fiscal year end_date from config is used."
        ),
    )
    ap.add_argument(
        "--to-date",
        dest="to_date",
        help=(
            "Custom period end date (YYYY-MM-DD). If provided without "
            "--from-date, the fiscal year start_date from config is used."
        ),
    )

    # Scope: what to render (statements, ratios, both)
    ap.add_argument(
        "--scope",
        choices=["statements", "all_statements", "ratios", "all"],
        default="statements",
        help=(
            "Select what to render: "
            "'statements' = primary statement only; "
            "'all_statements' = primary + secondary statement (if configured); "
            "'ratios' = ratios/KPIs only; "
            "'all' = statements and ratios."
        ),
    )

    # View: level of detail for statements
    ap.add_argument(
        "--view",
        choices=["simplified", "regular", "detailed", "complete"],
        default="detailed",
        help=(
            "Controls the level of detail of statement views. "
            "simplified: levels 0–1; regular: levels 0–2; "
            "detailed: all template levels; "
            "complete: detailed + account-level lines."
        ),
    )

    # Ratios level
    ap.add_argument(
        "--ratios-level",
        dest="ratios_level",
        choices=["basic", "advanced", "full"],
        help=(
            "Override the default ratios level defined in the configuration "
            "file. If omitted, the default level from config is used."
        ),
    )

    # Display options
    ap.add_argument(
        "--display-mode",
        dest="display_mode",
        choices=["table", "csv", "both"],
        help=(
            "Override the display.mode setting from the configuration file. "
            "'table' prints results to stdout, "
            "'csv' writes CSV files only, "
            "'both' does both."
        ),
    )
    ap.add_argument(
        "--output",
        dest="output_dir",
        help=(
            "Output directory where CSV files will be written when display "
            "mode includes 'csv'. "
            "If omitted, 'data/output' is used."
        ),
    )

    # ------------------------------------------------------------------
    # Subcommands: entries
    # ------------------------------------------------------------------
    subparsers = ap.add_subparsers(
        dest="command",
        metavar="command",
        help="Optional subcommands (e.g. 'entries') for inspecting data.",
    )

    # `entries` group: high-level operations on accounting entries.
    entries_parser = subparsers.add_parser(
        "entries",
        help="Inspect and manage accounting entries stored in the database.",
    )

    entries_subparsers = entries_parser.add_subparsers(
        dest="entries_command",
        metavar="entries-command",
        help="Entries subcommands (e.g. 'list').",
    )

    # ------------------------------------------------------------------
    # entries list
    # ------------------------------------------------------------------
    entries_list = entries_subparsers.add_parser(
        "list",
        help="List accounting entries for a reporting period.",
    )

    # Period selection (duplicated from top-level arguments so that
    # users can write: `entries list --period ytd`).
    entries_list.add_argument(
        "--period",
        choices=["fy", "ytd", "mtd", "last-month", "last-fy"],
        help=(
            "Named reporting period. If omitted, falls back to the default "
            "fiscal year behaviour defined in the configuration."
        ),
    )
    entries_list.add_argument(
        "--from-date",
        dest="from_date",
        help="Custom start date (YYYY-MM-DD). Overrides --period when set.",
    )
    entries_list.add_argument(
        "--to-date",
        dest="to_date",
        help="Custom end date (YYYY-MM-DD). Overrides --period when set.",
    )

    entries_list.add_argument(
        "--code",
        help="Filter by exact account code.",
    )
    entries_list.add_argument(
        "--code-prefix",
        dest="code_prefix",
        help="Filter by account code prefix (e.g. '70' for all 70* accounts).",
    )
    entries_list.add_argument(
        "--description-contains",
        dest="description_contains",
        help="Case-insensitive substring to search in the entry description.",
    )
    entries_list.add_argument(
        "--min-amount",
        dest="min_amount",
        type=float,
        help="Minimum amount (inclusive, in monetary units).",
    )
    entries_list.add_argument(
        "--max-amount",
        dest="max_amount",
        type=float,
        help="Maximum amount (inclusive, in monetary units).",
    )
    entries_list.add_argument(
        "--batch-id",
        dest="import_batch_id",
        type=int,
        help="Restrict to entries belonging to a specific import batch id.",
    )
    entries_list.add_argument(
        "--include-deleted",
        action="store_true",
        help="Include soft-deleted entries in the results.",
    )
    entries_list.add_argument(
        "--deleted-only",
        action="store_true",
        help="Return only soft-deleted entries.",
    )
    entries_list.add_argument(
        "--limit",
        type=int,
        help="Maximum number of entries to display (for pagination).",
    )
    entries_list.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Number of entries to skip before starting to display results.",
    )
    entries_list.add_argument(
        "--order-by",
        dest="order_by",
        choices=["date", "code", "amount", "id"],
        default="date",
        help="Column used to sort entries (default: date).",
    )
    entries_list.add_argument(
        "--order-direction",
        dest="order_direction",
        choices=["asc", "desc"],
        default="asc",
        help="Sort direction: 'asc' or 'desc' (default: asc).",
    )

    # ------------------------------------------------------------------
    # entries search
    # ------------------------------------------------------------------
    entries_search = entries_subparsers.add_parser(
        "search",
        help="Search accounting entries across the entire database.",
    )

    entries_search.add_argument(
        "--from-date",
        dest="from_date",
        help="Optional start date (YYYY-MM-DD) for filtering entries.",
    )
    entries_search.add_argument(
        "--to-date",
        dest="to_date",
        help="Optional end date (YYYY-MM-DD) for filtering entries.",
    )
    entries_search.add_argument(
        "--code",
        help="Filter by exact account code.",
    )
    entries_search.add_argument(
        "--code-prefix",
        dest="code_prefix",
        help="Filter by account code prefix (e.g. '70' for all 70* accounts).",
    )
    entries_search.add_argument(
        "--description-contains",
        dest="description_contains",
        help="Case-insensitive substring to search in the entry description.",
    )
    entries_search.add_argument(
        "--min-amount",
        dest="min_amount",
        type=float,
        help="Minimum amount (inclusive, in monetary units).",
    )
    entries_search.add_argument(
        "--max-amount",
        dest="max_amount",
        type=float,
        help="Maximum amount (inclusive, in monetary units).",
    )
    entries_search.add_argument(
        "--batch-id",
        dest="import_batch_id",
        type=int,
        help="Restrict to entries belonging to a specific import batch id.",
    )
    entries_search.add_argument(
        "--include-deleted",
        action="store_true",
        help="Include soft-deleted entries in the results.",
    )
    entries_search.add_argument(
        "--deleted-only",
        action="store_true",
        help="Return only soft-deleted entries.",
    )
    entries_search.add_argument(
        "--limit",
        type=int,
        help="Maximum number of entries to display (for pagination).",
    )
    entries_search.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Number of entries to skip before starting to display results.",
    )
    entries_search.add_argument(
        "--order-by",
        dest="order_by",
        choices=["date", "code", "amount", "id"],
        default="date",
        help="Column used to sort entries (default: date).",
    )
    entries_search.add_argument(
        "--order-direction",
        dest="order_direction",
        choices=["asc", "desc"],
        default="asc",
        help="Sort direction: 'asc' or 'desc' (default: asc).",
    )

    # ------------------------------------------------------------------
    # entries delete
    # ------------------------------------------------------------------
    entries_delete = entries_subparsers.add_parser(
        "delete",
        help="Soft-delete a single accounting entry by id.",
    )

    entries_delete.add_argument(
        "entry_id",
        type=int,
        help="Identifier of the entry to delete.",
    )
    entries_delete.add_argument(
        "--reason",
        help=(
            "Optional human-readable reason for the deletion. "
            "This is stored in the database and can be displayed in "
            "a recycle-bin view or for audit purposes."
        ),
    )

    # ------------------------------------------------------------------
    # entries restore
    # ------------------------------------------------------------------
    entries_restore = entries_subparsers.add_parser(
        "restore",
        help="Restore a previously soft-deleted accounting entry by id.",
    )

    entries_restore.add_argument(
        "entry_id",
        type=int,
        help="Identifier of the entry to restore.",
    )

    # ------------------------------------------------------------------
    # entries unknown-accounts
    # ------------------------------------------------------------------
    entries_unknown = entries_subparsers.add_parser(
        "unknown-accounts",
        help=(
            "Report on accounting entries whose account code is not present "
            "in the chart of accounts for the active standard."
        ),
    )

    # Period selection (same behaviour as 'entries list').
    entries_unknown.add_argument(
        "--period",
        choices=["fy", "ytd", "mtd", "last-month", "last-fy"],
        help=(
            "Named reporting period. If omitted, falls back to the default "
            "fiscal year behaviour defined in the configuration."
        ),
    )
    entries_unknown.add_argument(
        "--from-date",
        dest="from_date",
        help="Custom start date (YYYY-MM-DD). Overrides --period when set.",
    )
    entries_unknown.add_argument(
        "--to-date",
        dest="to_date",
        help="Custom end date (YYYY-MM-DD). Overrides --period when set.",
    )
    entries_unknown.add_argument(
        "--show-entries",
        action="store_true",
        help=(
            "Also display the full list of unknown entries, not only the "
            "summary per account code."
        ),
    )

    return ap


def _parse_optional_date(value: Optional[str]) -> Optional[date]:
    """
    Parse an optional CLI date argument (YYYY-MM-DD).

    Parameters
    ----------
    value:
        String value passed from the CLI, or None.

    Returns
    -------
    datetime.date or None
        Parsed date if value is not None, otherwise None.

    Raises
    ------
    SystemExit
        If the date format is invalid.
    """
    if value is None:
        return None

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        msg = f"Invalid date format: {value!r}. Expected YYYY-MM-DD."
        raise SystemExit(msg) from exc


def _handle_entries_list(args: argparse.Namespace, config) -> None:
    """
    Handle the 'entries list' subcommand: list accounting entries for a period
    with optional filters.

    This function:
    - determines the reporting period from CLI args and configuration,
    - builds an EntriesFilter from CLI-supplied filters,
    - uses entries_service.list_entries_for_period to load data,
    - prints a concise tabular view of the results to stdout.
    """
    # 1) Determine reporting period from CLI args (same logic as main).
    period = determine_period_from_args(args, config.fiscal_year)

    # 2) Build additional filters from CLI options.
    extra_filters = EntriesFilter(
        start=None,
        end=None,
        code_exact=args.code,
        code_prefix=args.code_prefix,
        description_contains=args.description_contains,
        min_amount=args.min_amount,
        max_amount=args.max_amount,
        import_batch_id=args.import_batch_id,
        include_deleted=args.include_deleted,
        deleted_only=args.deleted_only,
    )

    order = (args.order_by, args.order_direction.upper())

    # 3) Fetch entries using the high-level service.
    df = list_entries_for_period(
        config,
        period,
        extra_filters=extra_filters,
        limit=args.limit,
        offset=args.offset,
        order_by=order,
    )

    print(
        f"Applied period: {period.label} "
        f"({period.start.isoformat()} → {period.end.isoformat()})"
    )

    if df.empty:
        print("No entries found for the given criteria.")
        return

    # 4) Prepare a readable subset of columns for console display.
    preferred_columns = [
        "id",
        "date",
        "code",
        "description",
        "amount",
        "import_batch_id",
        "source_type",
        "is_deleted",
    ]
    columns_to_show = [c for c in preferred_columns if c in df.columns]
    if not columns_to_show:
        columns_to_show = list(df.columns)

    df_display = df[columns_to_show].copy()

    # Ensure date is displayed as ISO strings.
    if "date" in df_display.columns:
        df_display["date"] = df_display["date"].astype(str)

    # Print a compact table without the pandas index.
    print()
    print(df_display.to_string(index=False))

    # Optional footer with basic stats.
    if "amount" in df.columns:
        total_amount = float(df["amount"].sum())
        print()
        print(f"Total entries: {len(df)} | Total amount: {total_amount:.2f}")


def _handle_entries_search(args: argparse.Namespace, config) -> None:
    """
    Handle the 'entries search' subcommand: free-form search across the
    entire database using EntriesFilter.

    Unlike 'entries list', this command does not rely on a named reporting
    period. Optional date bounds can be provided via --from-date and
    --to-date, but if omitted, the search spans the whole dataset.
    """
    start_date = _parse_optional_date(args.from_date)
    end_date = _parse_optional_date(args.to_date)

    filters = EntriesFilter(
        start=start_date,
        end=end_date,
        code_exact=args.code,
        code_prefix=args.code_prefix,
        description_contains=args.description_contains,
        min_amount=args.min_amount,
        max_amount=args.max_amount,
        import_batch_id=args.import_batch_id,
        include_deleted=args.include_deleted,
        deleted_only=args.deleted_only,
    )

    order = (args.order_by, args.order_direction.upper())

    df = service_search_entries(
        config,
        filters,
        limit=args.limit,
        offset=args.offset,
        order_by=order,
    )

    if start_date or end_date:
        label_parts: list[str] = []
        if start_date:
            label_parts.append(f"from {start_date.isoformat()}")
        if end_date:
            label_parts.append(f"to {end_date.isoformat()}")
        label = " ".join(label_parts)
        print(f"Applied date bounds: {label}")
    else:
        print("No date bounds applied (searching across the whole dataset).")

    if df.empty:
        print("No entries found for the given criteria.")
        return

    preferred_columns = [
        "id",
        "date",
        "code",
        "description",
        "amount",
        "import_batch_id",
        "source_type",
        "is_deleted",
    ]
    columns_to_show = [c for c in preferred_columns if c in df.columns]
    if not columns_to_show:
        columns_to_show = list(df.columns)

    df_display = df[columns_to_show].copy()

    if "date" in df_display.columns:
        df_display["date"] = df_display["date"].astype(str)

    print()
    print(df_display.to_string(index=False))

    if "amount" in df.columns:
        total_amount = float(df["amount"].sum())
        print()
        print(f"Total entries: {len(df)} | Total amount: {total_amount:.2f}")


def _handle_entries_delete(args: argparse.Namespace, config) -> None:
    """
    Handle the 'entries delete' subcommand: soft-delete a single entry.

    This marks the entry as deleted (is_deleted=1) and records an optional
    deletion reason and timestamps in the database. The entry is not removed
    physically and can be restored later.
    """
    entry_id = args.entry_id
    reason = args.reason

    print(f"Soft-deleting entry #{entry_id}...")
    entry = service_delete_entry(config, entry_id, reason)

    # Display a concise summary of the deleted entry.
    print("Entry marked as deleted:")
    print(f"  id:            {entry.id}")
    print(f"  date:          {entry.date.isoformat()}")
    print(f"  code:          {entry.code}")
    print(f"  description:   {entry.description}")
    print(f"  amount:        {entry.amount:.2f}")
    print(f"  import_batch:  {entry.import_batch_id}")
    print(f"  source_type:   {entry.source_type}")
    print(f"  is_deleted:    {entry.is_deleted}")
    print(f"  deleted_at:    {entry.deleted_at}")

    reason_display = entry.deleted_reason or ""
    print(f"  deleted_reason: {reason_display}")


def _handle_entries_restore(args: argparse.Namespace, config) -> None:
    """
    Handle the 'entries restore' subcommand: restore a soft-deleted entry.

    This clears the deletion flags (is_deleted, deleted_at, deleted_reason)
    and updates the updated_at timestamp in the database.
    """
    entry_id = args.entry_id

    print(f"Restoring entry #{entry_id}...")
    entry = service_restore_entry(config, entry_id)

    print("Entry restored:")
    print(f"  id:             {entry.id}")
    print(f"  date:           {entry.date.isoformat()}")
    print(f"  code:           {entry.code}")
    print(f"  description:    {entry.description}")
    print(f"  amount:         {entry.amount:.2f}")
    print(f"  import_batch:   {entry.import_batch_id}")
    print(f"  source_type:    {entry.source_type}")
    print(f"  is_deleted:     {entry.is_deleted}")
    print(f"  deleted_at:     {entry.deleted_at}")
    reason_display = entry.deleted_reason or ""
    print(f"  deleted_reason: {reason_display}")


def _handle_entries_unknown_accounts(args: argparse.Namespace, config) -> None:
    """
    Handle the 'entries unknown-accounts' subcommand.

    This command:
    - determines the reporting period from CLI args,
    - builds the unknown-accounts report using the chart of accounts of the
      active standard,
    - prints a summary of unknown accounts (code, number of entries, total),
    - optionally prints the full list of unknown entries.
    """
    # 1) Déterminer la période (même logique que pour entries list).
    period = determine_period_from_args(args, config.fiscal_year)

    print(
        f"Applied period: {period.label} "
        f"({period.start.isoformat()} → {period.end.isoformat()})"
    )

    # 2) Construire le rapport via le service.
    try:
        known_entries, unknown_entries, summary = service_unknown_accounts_report(
            config,
            period,
        )
    except ValueError as exc:
        # Typiquement: chart_of_accounts non configuré pour le standard actif.
        print(f"Error while building unknown accounts report: {exc}")
        return

    if unknown_entries.empty:
        print("No unknown accounts detected for the given period.")
        return

    # 3) Afficher le résumé par code (summary).
    print()
    print("Unknown accounts summary (grouped by account code):")

    # On s'assure de l'ordre des colonnes pour la lisibilité.
    summary_cols = [
        c for c in ["code", "entries_count", "total_amount"] if c in summary.columns
    ]
    summary_display = summary[summary_cols].copy()
    print(summary_display.to_string(index=False))

    # 4) Optionnellement, afficher la liste détaillée des écritures inconnues.
    if args.show_entries:
        print()
        print("Unknown entries:")
        preferred_columns = [
            "date",
            "code",
            "description",
            "amount",
            "import_batch_id",
            "source_type",
        ]
        cols_to_show = [c for c in preferred_columns if c in unknown_entries.columns]
        if not cols_to_show:
            cols_to_show = list(unknown_entries.columns)

        df_unknown_display = unknown_entries[cols_to_show].copy()
        if "date" in df_unknown_display.columns:
            df_unknown_display["date"] = df_unknown_display["date"].astype(str)

        print(df_unknown_display.to_string(index=False))


def _handle_entries_command(args: argparse.Namespace, config) -> None:
    """
    Dispatch function for the 'entries' subcommands.

    This is called from main() after the database has been initialized
    and optional CSV import has been performed.
    """
    subcmd = getattr(args, "entries_command", None)

    if subcmd == "list":
        _handle_entries_list(args, config)
    elif subcmd == "search":
        _handle_entries_search(args, config)
    elif subcmd == "delete":
        _handle_entries_delete(args, config)
    elif subcmd == "restore":
        _handle_entries_restore(args, config)
    elif subcmd == "unknown-accounts":
        _handle_entries_unknown_accounts(args, config)
    else:
        print(
            "No entries subcommand specified. "
            "Available subcommands are: "
            "'list', 'search', 'delete', 'restore', 'unknown-accounts'."
        )


def main() -> None:
    """Entry point for the SMB FinSight CLI.

    This function parses command-line arguments, loads the application and
    standard-specific configuration, initializes the database, optionally
    imports accounting entries from a CSV file into the database, reads the
    chart of accounts, loads accounting entries for the selected period from
    the database, aggregates primary and optional secondary statements,
    optionally computes ratios/KPIs, and finally renders the selected scope
    as console tables and/or CSV files.
    """
    parser = _build_parser()
    args = parser.parse_args()

    # --version: short-circuit and exit early.
    if args.version:
        print(f"smb_finsight version {__version__}")
        return

    # 1) Load application configuration (fiscal year, standard, paths, ratios, display)
    if args.config_path:
        config = load_app_config(args.config_path)
    else:
        config = load_app_config()

    std_cfg = config.standard_config

    # 2) Initialize the database (create file and schema if needed)
    init_database(config.database)

    # After init_database(config.database)
    if not args.import_path and not has_entries(config.database):
        print("Warning: database is empty — use --import to load accounting entries.")

    # 3) Optional import from CSV into the database
    if args.import_path:
        csv_path = Path(args.import_path)
        if not csv_path.is_file():
            parser.error(f"CSV file for --import not found: {csv_path}")

        print(f"Importing accounting entries from {csv_path} into the database...")
        df_import = read_accounting_entries(csv_path)
        stats = import_entries(
            df_import,
            config.database,
            source_type="csv",
            source_label=str(csv_path),
        )
        print(
            f"Imported batch #{stats.batch_id}: "
            f"{stats.rows_inserted} entries, "
            f"{stats.duplicates_detected} potential duplicates."
        )

    # If an 'entries' subcommand was requested, handle it now and exit early.
    if getattr(args, "command", None) == "entries":
        _handle_entries_command(args, config)
        return

    # 4) Resolve paths with optional CLI overrides for mappings and chart of accounts
    primary_mapping_path: Optional[Path] = (
        Path(args.income_statement_mapping)
        if args.income_statement_mapping
        else std_cfg.income_statement_mapping
    )
    if primary_mapping_path is None:
        parser.error(
            "No primary income statement mapping configured. "
            "Either set it in the standard config or provide "
            "--income-statement-mapping."
        )

    secondary_mapping_path: Optional[Path] = (
        Path(args.secondary_mapping)
        if args.secondary_mapping
        else std_cfg.secondary_mapping
    )

    chart_of_accounts_path: Optional[Path] = (
        Path(args.chart_of_accounts)
        if args.chart_of_accounts
        else std_cfg.chart_of_accounts
    )
    if chart_of_accounts_path is None:
        parser.error(
            "No chart of accounts configured. "
            "Either set it in the standard config or provide --chart-of-accounts."
        )

    # 5) Load the user-maintained chart of accounts.
    accounts_df = load_list_of_accounts(chart_of_accounts_path)
    known_codes = set(accounts_df["account_number"])
    name_by_code = dict(zip(accounts_df["account_number"], accounts_df["name"]))

    # 6) Determine reporting period.
    period = determine_period_from_args(args, config.fiscal_year)

    # 7) Load accounting entries for the selected period from the database.
    tx_raw = load_entries(config.database, period.start, period.end)

    print(
        f"Applied period: {period.label} "
        f"({period.start.isoformat()} → {period.end.isoformat()})"
    )
    print(f"Entries retrieved from database for period: {len(tx_raw)}")
    if len(tx_raw) == 0:
        print(
            "Warning: no accounting entries were found in the database for "
            "the selected period."
        )

    # 8) Filter out entries whose account code is unknown.
    tx = filter_unknown_accounts(tx_raw, known_codes)

    # Evaluate which parts of the pipeline are needed based on scope.
    scope = args.scope
    want_primary_statement = scope in {"statements", "all_statements", "all"}
    want_secondary_statement = secondary_mapping_path is not None and scope in {
        "all_statements",
        "all",
    }
    want_ratios = scope in {"ratios", "all"} and config.ratios_enabled

    if scope in {"ratios", "all"} and not config.ratios_enabled:
        print(
            "Ratios have been requested in scope, but ratios are disabled in the "
            "configuration (ratios.enabled = false). Skipping ratio computation."
        )

    # 7) Aggregate primary statement.
    primary_template = Template.from_csv(primary_mapping_path)
    primary_base = aggregate(tx, primary_template)

    if args.view == "complete":
        primary_view = build_complete_view(
            out_base=primary_base,
            accounting_entries=tx,
            template=primary_template,
            name_by_code=name_by_code,
        )
    else:
        primary_view = apply_view_level_filter(primary_base, args.view)

    # 8) Aggregate secondary statement if configured.
    # We may need secondary measures for ratios even if we do not display
    # the secondary statement itself.
    secondary_view = None
    secondary_template = None
    secondary_base = None
    if secondary_mapping_path is not None and (want_secondary_statement or want_ratios):
        secondary_template = Template.from_csv(secondary_mapping_path)
        secondary_base = aggregate(tx, secondary_template)

        # Only build a view for display if a secondary statement was requested
        # in the scope. For secondary statements (e.g. SIG under FR PCG), we do
        # not perform account-level drill-down: even if the requested view is
        # "complete", we fall back to the detailed template view.
        if want_secondary_statement:
            if args.view == "complete":
                secondary_view = apply_view_level_filter(secondary_base, "detailed")
            else:
                secondary_view = apply_view_level_filter(secondary_base, args.view)

    # 9) Build canonical measures and compute ratios if requested.
    ratios_df = None
    if want_ratios:
        if std_cfg.ratios_rules_file is None:
            print(
                "Ratios have been requested (scope includes 'ratios') but no "
                "ratios.rules_file is configured for this accounting standard."
            )
        else:
            extra_measures = {
                **config.balance_sheet_inputs,
                **config.hr_inputs,
                "period_days": float(config.period_days),
            }

            measures = build_canonical_measures(
                statement=primary_base,
                template=primary_template,
                extra_measures=extra_measures,
            )

            if secondary_template is not None:
                secondary_measures = build_canonical_measures(
                    statement=secondary_base,
                    template=secondary_template,
                )
                measures.update(secondary_measures)

            # Derived measures
            all_measures = compute_derived_measures(
                base_measures=measures,
                rules_file=std_cfg.ratios_rules_file,
            )

            # Optional custom ratios pack (if configured)
            if std_cfg.ratios_custom_file is not None:
                all_measures = compute_derived_measures(
                    base_measures=all_measures,
                    rules_file=std_cfg.ratios_custom_file,
                )

            # Ratios level: CLI override or config default
            ratio_level = args.ratios_level or config.default_ratios_level

            ratios_list = compute_ratios(
                measures=all_measures,
                rules_file=std_cfg.ratios_rules_file,
                level=ratio_level,
            )
            ratios_df = ratios_to_dataframe(
                ratios_list,
                decimals=config.ratio_decimals,
            )

    # 10) Resolve display mode: config value overridden by CLI if provided.
    display_mode = config.display_mode
    if args.display_mode:
        display_mode = args.display_mode

    # 11) Render to console (table mode).
    if display_mode in {"table", "both"}:
        if want_primary_statement:
            print()
            print(f"=== {std_cfg.primary_statement_label} ===")
            print(primary_view.to_string(index=False))

        if want_secondary_statement and secondary_view is not None:
            if std_cfg.secondary_statement_label:
                label = std_cfg.secondary_statement_label
            else:
                label = "Secondary statement"
            print()
            print(f"=== {label} ===")
            print(secondary_view.to_string(index=False))

        if want_ratios and ratios_df is not None:
            print()
            print("=== Ratios & KPIs ===")
            print(ratios_df.to_string(index=False))

    # 12) Render to CSV files (csv mode).
    if display_mode in {"csv", "both"}:
        output_dir = Path(args.output_dir) if args.output_dir else Path("data/output")
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")

        if want_primary_statement:
            path = output_dir / f"income_statement_{timestamp}.csv"
            primary_view.to_csv(path, index=False)
            print(f"Wrote {path} ({len(primary_view)} rows)")

        if want_secondary_statement and secondary_view is not None:
            path = output_dir / f"secondary_statement_{timestamp}.csv"
            secondary_view.to_csv(path, index=False)
            print(f"Wrote {path} ({len(secondary_view)} rows)")

        if want_ratios and ratios_df is not None:
            path = output_dir / f"ratios_{timestamp}.csv"
            ratios_df.to_csv(path, index=False)
            print(f"Wrote {path} ({len(ratios_df)} rows)")


if __name__ == "__main__":
    main()
