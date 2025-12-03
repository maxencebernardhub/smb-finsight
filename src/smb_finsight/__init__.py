# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
SMB FinSight
------------

A Python-based financial analysis and reporting application designed for
Small and Medium-sized Businesses (SMBs). The project provides a modular,
standard-agnostic computation engine and a flexible command-line interface.

Main capabilities:
- multi-standard income statement generation (FR PCG, CA ASPE, US GAAP, IFRS),
- optional secondary statements (e.g. Soldes Intermédiaires de Gestion – SIG),
- canonical measures and derived KPI computation,
- configurable ratios engine with multi-level output,
- a powerful single-period analytics pipeline,
- a unified multi-period computation engine (v0.3.5+),
- a database-first architecture for accounting entries (SQLite),
- a complete CRUD interface for accounting entries (v0.4.0+),
- unknown accounts detection & reporting (v0.4.0+),
- duplicate detection & full duplicate resolution workflow (v0.4.5+),
- foundation for the upcoming Web UI (v0.5.x).

SMB FinSight separates computation (engine), configuration (TOML), and
presentation (CLI / Web UI), making it suitable for scripting, automation,
consulting workflows, and financial diagnostics.


Version: 0.4.5

Usage:
    python -m smb_finsight.cli --help
"""

__all__ = ["engine", "mapping", "views", "io"]

__version__ = "0.4.5"
