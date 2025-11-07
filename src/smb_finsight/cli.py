# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

import argparse

from . import __version__
from .engine import aggregate
from .io import read_accounting_entries
from .mapping import Template


def main():
    ap = argparse.ArgumentParser(
        prog="smb-finsight",
        description="Aggregate accounting_entries to Income Statement.",
    )
    ap.add_argument(
        "--accounting_entries",
        required=False,
        help="Path to CSV file containing accounting entries.",
    )
    ap.add_argument(
        "--template",
        required=False,
        help="Path to mapping template CSV file (simplified or regular).",
    )
    ap.add_argument("--output", required=False, help="Path to output CSV file.")
    ap.add_argument(
        "--version",
        action="store_true",
        help="Show the current version of SMB FinSight and exit.",
    )
    args = ap.parse_args()

    if args.version:
        print(f"SMB FinSight version {__version__}")
        return

    if not args.accounting_entries or not args.template or not args.output:
        ap.print_help()
        return

    tx = read_accounting_entries(args.accounting_entries)
    tpl = Template.from_csv(args.template)
    out = aggregate(tx, tpl)
    out.to_csv(args.output, index=False)
    print(f"Wrote {args.output} ({len(out)} rows)")


if __name__ == "__main__":
    main()
