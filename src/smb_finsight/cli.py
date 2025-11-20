# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Command-Line Interface (CLI) for SMB FinSight.

This module wires together the main building blocks of SMB FinSight:

- global configuration (fiscal year, paths, display options),
- standard-specific configuration (mapping templates, ratios rules),
- accounting entries I/O,
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

- ``--accounting-entries``:
    Override the accounting entries CSV path.
- ``--income-statement-mapping``:
    Override the primary statement mapping CSV path.
- ``--secondary-mapping``:
    Override the secondary statement mapping CSV path.
- ``--chart-of-accounts``:
    Override the chart of accounts CSV path.

These overrides only affect the current CLI run and leave the TOML
configuration unchanged.


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

"""

import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import __version__
from .accounts import filter_unknown_accounts, load_list_of_accounts
from .config import load_app_config
from .engine import aggregate, build_canonical_measures
from .io import read_accounting_entries
from .mapping import Template
from .periods import determine_period_from_args, filter_entries_by_period
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

    # Path overrides (optional, override TOML config)
    ap.add_argument(
        "--accounting-entries",
        dest="accounting_entries",
        help=(
            "Override the accounting entries CSV path defined in the main "
            "configuration file."
        ),
    )
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

    return ap


def main() -> None:
    """Entry point for the SMB FinSight CLI.

    This function parses command-line arguments, loads the application and
    standard-specific configuration, reads the chart of accounts and the
    accounting entries, applies the fiscal period selection, aggregates
    primary and optional secondary statements, optionally computes ratios/KPIs,
    and finally renders the selected scope as console tables and/or CSV files.
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

    # 2) Resolve paths with optional CLI overrides
    accounting_entries_path: Optional[Path] = (
        Path(args.accounting_entries)
        if args.accounting_entries
        else config.accounting_entries_path
    )

    if accounting_entries_path is None:
        parser.error(
            "No accounting entries path configured. "
            "Either set it in the main config or provide --accounting-entries."
        )

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

    # 3) Load the user-maintained chart of accounts.
    accounts_df = load_list_of_accounts(chart_of_accounts_path)
    known_codes = set(accounts_df["account_number"])
    name_by_code = dict(zip(accounts_df["account_number"], accounts_df["name"]))

    # 4) Read and normalize accounting entries.
    tx_raw = read_accounting_entries(accounting_entries_path)

    # 5) Determine reporting period and filter entries.
    period = determine_period_from_args(args, config.fiscal_year)
    tx_period = filter_entries_by_period(tx_raw, period)

    print(
        f"Applied period: {period.label} "
        f"({period.start.isoformat()} → {period.end.isoformat()})"
    )
    print(f"Entries kept after period filter: {len(tx_period)}")
    if len(tx_period) == 0:
        print("Warning: no accounting entries fall inside the selected period.")

    # 6) Filter out entries whose account code is unknown.
    tx = filter_unknown_accounts(tx_period, known_codes)

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
