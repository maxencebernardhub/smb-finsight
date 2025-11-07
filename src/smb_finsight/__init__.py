# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
SMB FinSight
------------

A financial dashboard & analysis tool for Small and Medium Businesses (SMBs).

Modules:
- engine: Core aggregation logic for income statement generation.
- mapping: Handles PCG mapping templates and formula evaluation.
- io: Input/output utilities for reading accounting entries (CSV).

Usage example:
    python -m smb_finsight.cli --help
"""

__all__ = ["engine", "mapping", "io"]

__version__ = "0.1.1"
