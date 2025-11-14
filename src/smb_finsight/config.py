# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Configuration loading for SMB FinSight.

This module is responsible for loading the current fiscal year definition
from a simple TOML configuration file.

Expected TOML structure
-----------------------

    [fiscal_year]
    start_date = "YYYY-MM-DD"
    end_date   = "YYYY-MM-DD"

Example
-------

    [fiscal_year]
    start_date = "2025-01-01"
    end_date   = "2025-12-31"

If the file is missing or malformed, a ValueError is raised. Interactive
initialization (asking dates via CLI and writing the file) can be added
in a future version.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import tomllib  # Python 3.11+

CONFIG_FILENAME = "smb_finsight_config.toml"


@dataclass
class FiscalYear:
    """Simple value object representing a fiscal year."""

    start_date: date
    end_date: date


def load_fiscal_year(config_path: Optional[str] = None) -> FiscalYear:
    """
    Load the current fiscal year definition from a TOML configuration file.

    Parameters
    ----------
    config_path:
        Optional explicit path to the TOML config file. If omitted, the
        default filename ``smb_finsight_config.toml`` is used in the
        current working directory.

    Returns
    -------
    FiscalYear
        The loaded fiscal year with validated start and end dates.

    Raises
    ------
    ValueError
        If the file does not exist, if required keys are missing, or if
        date values are invalid or inconsistent.
    """
    cfg_path = Path(config_path) if config_path else Path(CONFIG_FILENAME)

    if not cfg_path.exists():
        raise ValueError(
            f"Config file '{cfg_path}' not found. Expected a file with:\n"
            "[fiscal_year]\nstart_date = 'YYYY-MM-DD'\nend_date   = 'YYYY-MM-DD'"
        )

    with cfg_path.open("rb") as f:
        data = tomllib.load(f)

    try:
        fy_data = data["fiscal_year"]
        start_raw = fy_data["start_date"]
        end_raw = fy_data["end_date"]
    except KeyError as exc:  # noqa: BLE001
        raise ValueError(
            "Config file is missing [fiscal_year] / start_date / end_date keys."
        ) from exc

    try:
        start = date.fromisoformat(start_raw)
        end = date.fromisoformat(end_raw)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            "Invalid fiscal year dates, expected YYYY-MM-DD format."
        ) from exc

    if end < start:
        raise ValueError("Fiscal year end_date cannot be before start_date.")

    return FiscalYear(start_date=start, end_date=end)
