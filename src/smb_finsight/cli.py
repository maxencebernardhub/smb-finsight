# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Command-Line Interface (CLI) for SMB FinSight.

The CLI orchestrates the main pipeline:
1) read accounting entries from a CSV file,
2) load a PCG-based mapping template,
3) load and apply the user-maintained list of accounts (chart of accounts),
4) aggregate amounts into income-statement rows,
5) transform the result into one of the supported views,
6) write the final statement to a CSV file.

Supported views
---------------
- simplified: levels 0–1 (very aggregated view)
- regular:    levels 0–2 (standard income statement)
- detailed:   all template levels (0–3)
- complete:   detailed + account-level rows inserted under level-3 'acc' rows.

The list of accounts (list_of_accounts CSV) is used both to:
- validate that each accounting entry refers to a known account code;
- provide labels for account-level rows in the 'complete' view.
"""

import argparse

from . import __version__
from .accounts import filter_unknown_accounts, load_list_of_accounts
from .engine import aggregate
from .io import read_accounting_entries
from .mapping import Template
from .views import apply_view_level_filter, build_complete_view


def _build_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser for the CLI."""
    ap = argparse.ArgumentParser(
        prog="smb-finsight",
        description="Aggregate accounting_entries to Income Statement.",
    )
    ap.add_argument(
        "--accounting_entries",
        required=False,  # kept optional for version-only usage
        help="Path to CSV file containing accounting entries.",
    )
    ap.add_argument(
        "--template",
        required=False,
        help=(
            "Path to mapping template CSV file "
            "(e.g. detailed_income_statement_pcg.csv)."
        ),
    )
    ap.add_argument(
        "--output",
        required=False,
        help="Path to output CSV file.",
    )
    ap.add_argument(
        "--view",
        choices=["simplified", "regular", "detailed", "complete"],
        default="detailed",
        help=(
            "Controls the level of detail of the income statement view. "
            "simplified: levels 0–1; regular: levels 0–2; "
            "detailed: all template levels; complete: detailed + account-level lines."
        ),
    )
    ap.add_argument(
        "--list-of-accounts",
        required=False,
        dest="list_of_accounts",
        help=(
            "Path to the user-maintained list of accounts (chart of accounts) "
            "CSV, e.g. data/accounts/pcg.csv. "
            "Required for all views except --version."
        ),
    )
    ap.add_argument(
        "--version",
        action="store_true",
        help="Show the current version of SMB FinSight and exit.",
    )
    return ap


def main() -> None:
    """Entry point for `python -m smb_finsight.cli`."""
    parser = _build_parser()
    args = parser.parse_args()

    # Simple case: only display the current version.
    if args.version:
        print(f"SMB FinSight version {__version__}")
        return

    # Sanity checks: make sure all required paths are provided.
    if not args.accounting_entries or not args.template or not args.output:
        parser.print_help()
        return

    if not args.list_of_accounts:
        parser.error(
            "--list-of-accounts is required (path to accounts CSV, "
            "e.g. data/accounts/pcg.csv)"
        )

    # 1) Load the user-maintained chart of accounts.
    accounts_df = load_list_of_accounts(args.list_of_accounts)
    known_codes = set(accounts_df["account_number"])
    name_by_code = dict(zip(accounts_df["account_number"], accounts_df["name"]))

    # 2) Read and normalize accounting entries (code, amount).
    tx_raw = read_accounting_entries(args.accounting_entries)

    # 3) Filter out entries whose account code is unknown.
    tx = filter_unknown_accounts(tx_raw, known_codes)

    # 4) Load the mapping template.
    tpl = Template.from_csv(args.template)

    # 5) Aggregate via the core engine.
    out_base = aggregate(tx, tpl)

    # 6) Apply the selected view.
    if args.view == "complete":
        out = build_complete_view(
            out_base=out_base,
            accounting_entries=tx,
            template=tpl,
            name_by_code=name_by_code,
        )
    else:
        out = apply_view_level_filter(out_base, args.view)

    # 7) Write the output CSV.
    out.to_csv(args.output, index=False)
    print(f"Wrote {args.output} ({len(out)} rows)")


if __name__ == "__main__":
    main()
