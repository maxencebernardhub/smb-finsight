# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
SMB FinSight
------------

A Python-based financial dashboard & analysis application for Small and
Medium-sized Businesses (SMBs).

It aggregates accounting entries (accounts 6 & 7) into normalized income statements
based on the French *Plan Comptable Général* (PCG).

Modules:
- `engine`: Core aggregation logic for income statement generation.
- `mapping`: Handles PCG mapping templates and formula evaluation.
- `io`: Input/output utilities for reading accounting entries (CSV files).
- `cli`: Command-line interface for batch execution.

Usage example:
    python -m smb_finsight.cli --help
"""

__all__ = ["engine", "mapping", "io"]

__version__ = "0.1.1"
