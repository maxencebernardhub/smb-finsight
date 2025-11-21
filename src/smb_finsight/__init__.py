# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
SMB FinSight
------------

A Python-based financial dashboard & analysis application for Small and
Medium-sized Businesses (SMBs), providing:

- multi-standard income statement generation,
- support for optional secondary statements (e.g., French SIG),
- canonical financial measure computation,
- a configurable financial ratios & KPIs engine,
- a unified CLI for statements and ratios.

Version: 0.2.0

Usage:
    python -m smb_finsight.cli --help
"""

__all__ = ["engine", "mapping", "views", "io"]

__version__ = "0.2.0"
