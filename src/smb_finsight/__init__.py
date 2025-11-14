# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
SMB FinSight
------------

A Python-based financial dashboard & analysis application for Small and
Medium-sized Businesses (SMBs).

The application aggregates accounting entries (Plan Comptable Général – PCG)
into normalized income statement structures (simplified, regular, detailed,
complete, and SIG), with full support for:

- Mandatory accounting entry fields: date, code, description
- Debit/credit or signed-amount formats
- Fiscal-year configuration via `smb_finsight_config.toml`
- Period selection (FY, YTD, MTD, last-month, last-fy, custom)
- Accurate date-based filtering before aggregation

Modules:
- `engine`: Core aggregation logic for income-statement generation.
- `mapping`: Handles PCG mapping templates and formula evaluation.
- `views`: Output views (simplified, regular, detailed, complete, SIG).
- `io`: Input utilities for reading normalized accounting entry CSVs.
- `cli`: Command-line interface supporting period filtering and batch execution.

Usage:
    python -m smb_finsight.cli --help
"""

__all__ = ["engine", "mapping", "views", "io"]

__version__ = "0.1.5"
