# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
CLI (Command-Line Interface) for SMB FinSight.

This module provides a thin command-line wrapper around the core engine:
1) read accounting entries from a CSV file,
2) load a mapping template (simplified or regular french PCG),
3) aggregate amounts into income-statement rows,
4) write the result to a CSV file.

Usage:
    # Show help
    python -m smb_finsight.cli --help

    # Show version
    python -m smb_finsight.cli --version

    # Run with explicit files
    python -m smb_finsight.cli \
        --accounting_entries examples/accounting_entries.csv \
        --template data/mappings/simplified_income_statement_pcg.csv \
        --output examples/out_simplified.csv

Notes:
- This CLI intentionally keeps the same behavior and arguments as previous versions.
- No business logic is implemented here; it delegates to `io`, `mapping`, and `engine`.
"""

import argparse

from . import __version__
from .engine import aggregate
from .io import read_accounting_entries
from .mapping import Template


def main() -> None:
    """Entry point for `python -m smb_finsight.cli`.

    Behavior:
        - If --version is provided, print the current version and exit.
        - If any of (--accounting_entries, --template, --output) is missing,
          print help and exit (no processing).
        - Otherwise, run the end-to-end flow:
            read CSV -> load template -> aggregate -> write CSV -> print summary.
    """
    # Build the CLI parser and declare arguments.
    ap = argparse.ArgumentParser(
        prog="smb-finsight",
        description="Aggregate accounting_entries to Income Statement.",
    )
    ap.add_argument(
        "--accounting_entries",
        required=False,  # kept for full backward compatibility
        help=(
            "Path to CSV file containing accounting entries "
            "(with debit/credit columns)."
        ),
    )
    ap.add_argument(
        "--template",
        required=False,  # kept for full backward compatibility
        help="Path to mapping template CSV file (simplified or regular PCG).",
    )
    ap.add_argument(
        "--output",
        required=False,  # kept for full backward compatibility
        help="Path to output CSV file to write.",
    )
    ap.add_argument(
        "--version",
        action="store_true",
        help="Show the current version of SMB FinSight and exit.",
    )

    # Parse CLI args
    args = ap.parse_args()

    # Fast path: version only
    if args.version:
        print(f"SMB FinSight version {__version__}")
        return

    # Guard: if any required path is missing, show help and exit gracefully.
    if not args.accounting_entries or not args.template or not args.output:
        ap.print_help()
        return

    # 1) Read & normalize accounting entries (amount = credit - debit).
    tx = read_accounting_entries(args.accounting_entries)

    # 2) Load mapping template (rows, patterns, formulas).
    tpl = Template.from_csv(args.template)

    # 3) Aggregate per template rows and compute formula rows.
    out = aggregate(tx, tpl)

    # 4) Persist to CSV and inform the user.
    out.to_csv(args.output, index=False)

    print(f"Wrote {args.output} ({len(out)} rows)")


if __name__ == "__main__":
    main()
