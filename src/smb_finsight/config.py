# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Configuration helpers for SMB FinSight.

This module is responsible for:
- loading the main application configuration from a TOML file,
- loading the standard-specific configuration (FR_PCG, CA_ASPE, etc.),
- exposing typed dataclasses used by the rest of the application.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Optional

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - fallback for older Python
    import tomli as tomllib  # type: ignore[import]

from .db import DatabaseConfig


@dataclass(frozen=True)
class FiscalYear:
    """Represents a fiscal year with a start and end date."""

    start_date: date
    end_date: date


@dataclass(frozen=True)
class StandardConfig:
    """
    Standard-specific configuration.

    This structure holds all configuration that depends on the accounting
    standard (FR_PCG, CA_ASPE, US_GAAP, IFRS, etc.), as defined in a
    standard-specific TOML file (for example: config/standard_fr_pcg.toml).
    """

    standard: str
    income_statement_mapping: Optional[Path]
    secondary_mapping: Optional[Path]
    chart_of_accounts: Optional[Path]
    ratios_rules_file: Optional[Path]
    ratios_custom_file: Optional[Path]
    primary_statement_label: str
    secondary_statement_label: Optional[str]


@dataclass(frozen=True)
class AppConfig:
    """
    Application-wide configuration for SMB FinSight.

    This aggregates:
    - the fiscal year definition,
    - the main accounting standard and currency,
    - the database configuration (where entries are stored),
    - the standard-specific configuration (mappings, ratios rules),
    - optional inputs for balance sheet, HR and period parameters,
    - global ratios options,
    - display options for tables and ratios.
    """

    fiscal_year: FiscalYear
    standard: str
    currency: str
    database: DatabaseConfig
    standard_config: StandardConfig
    balance_sheet_inputs: dict[str, float]
    hr_inputs: dict[str, float]
    period_days: int
    ratios_enabled: bool
    default_ratios_level: str
    display_mode: str
    ratio_decimals: int


def _load_toml(path: Path) -> dict[str, Any]:
    """
    Load a TOML file and return its content as a dictionary.

    Raises:
        FileNotFoundError: if the file does not exist.
        ValueError: if the TOML content cannot be parsed or is not a table.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Config file not found: {path}")

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Failed to parse TOML config file: {path}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"Invalid TOML root type in {path}, expected a table.")

    return data


def _parse_fiscal_year(config_data: Mapping[str, Any]) -> FiscalYear:
    """
    Extract and validate the fiscal year from raw TOML configuration data.

    Args:
        config_data: Parsed TOML root dictionary.

    Returns:
        A FiscalYear instance.

    Raises:
        ValueError: if the fiscal year section or dates are missing/invalid.
    """
    fiscal_data = config_data.get("fiscal_year") or {}
    if not isinstance(fiscal_data, Mapping):
        raise ValueError("Config file is missing [fiscal_year] table.")

    try:
        start_raw = fiscal_data["start_date"]
        end_raw = fiscal_data["end_date"]
    except KeyError as exc:
        raise ValueError(
            "Config file is missing [fiscal_year].start_date or end_date."
        ) from exc

    try:
        start = date.fromisoformat(str(start_raw))
        end = date.fromisoformat(str(end_raw))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(
            "Invalid fiscal year dates, expected YYYY-MM-DD format."
        ) from exc

    if end < start:
        raise ValueError("Fiscal year end_date cannot be before start_date.")

    return FiscalYear(start_date=start, end_date=end)


def _parse_standard_config(
    standard: str,
    standard_config_path_raw: Optional[str],
    base_dir: Path,
) -> StandardConfig:
    """
    Load and parse the standard-specific configuration file, if provided.

    Args:
        standard: Accounting standard name (FR_PCG, CA_ASPE, etc.).
        standard_config_path_raw: Relative or absolute path to the
            standard-specific config file, as read from smb_finsight_config.toml.
        base_dir: Base directory used to resolve relative paths.

    Returns:
        A StandardConfig instance. If no standard_config_path_raw is provided,
        all paths will be set to None.
    """
    if not standard_config_path_raw:
        return StandardConfig(
            standard=standard,
            income_statement_mapping=None,
            secondary_mapping=None,
            chart_of_accounts=None,
            ratios_rules_file=None,
            ratios_custom_file=None,
            primary_statement_label="Income statement",
            secondary_statement_label=None,
        )

    std_path = (base_dir / standard_config_path_raw).resolve()
    std_data = _load_toml(std_path)

    paths_section = std_data.get("paths") or {}
    if not isinstance(paths_section, Mapping):
        paths_section = {}

    mapping_section = paths_section.get("mapping") or {}
    if not isinstance(mapping_section, Mapping):
        mapping_section = {}

    ratios_section = std_data.get("ratios") or {}
    if not isinstance(ratios_section, Mapping):
        ratios_section = {}

    def _resolve_optional(rel: Optional[str]) -> Optional[Path]:
        if not rel:
            return None
        return (std_path.parent / rel).resolve()

    income_statement_mapping = _resolve_optional(
        mapping_section.get("income_statement")
    )

    # secondary_mapping can be defined explicitly
    secondary_raw = mapping_section.get("secondary_mapping")

    secondary_mapping = _resolve_optional(secondary_raw)

    chart_of_accounts = _resolve_optional(mapping_section.get("chart_of_accounts"))

    ratios_rules_file = _resolve_optional(ratios_section.get("rules_file"))
    ratios_custom_file = _resolve_optional(ratios_section.get("custom_rules_file"))

    statements_section = std_data.get("statements") or {}
    if not isinstance(statements_section, Mapping):
        statements_section = {}

    primary_label = str(statements_section.get("primary_label", "Income statement"))

    raw_secondary_label = statements_section.get("secondary_label")
    secondary_label: Optional[str]
    if raw_secondary_label is None or raw_secondary_label == "":
        secondary_label = None
    else:
        secondary_label = str(raw_secondary_label)

    return StandardConfig(
        standard=standard,
        income_statement_mapping=income_statement_mapping,
        secondary_mapping=secondary_mapping,
        chart_of_accounts=chart_of_accounts,
        ratios_rules_file=ratios_rules_file,
        ratios_custom_file=ratios_custom_file,
        primary_statement_label=primary_label,
        secondary_statement_label=secondary_label,
    )


def load_app_config(config_path: Optional[str] = None) -> AppConfig:
    """
    Load the SMB FinSight application configuration from a TOML file.

    The configuration aggregates all global settings required by the engine,
    database layer and CLI. Since version 0.3.0, SMB FinSight no longer reads
    accounting entries directly from CSV files defined in the config.
    Instead, *all* financial data is stored in and retrieved from the
    application database (see section [database]).

    Expected top-level sections in the TOML file
    --------------------------------------------
    [fiscal_year]
        Defines the fiscal year start date (month/day).

    [accounting]
        Defines the accounting standard (e.g. "FR_PCG", "CA_ASPE") and
        the presentation currency.

    [database]
        Defines the database engine and the SQLite file path.
        This is now mandatory: SMB FinSight always uses the database as
        the single source of truth for accounting entries.

    [inputs.balance_sheet]
        Optional manual inputs to enrich calculated ratios.

    [inputs.hr]
        Optional human-resources inputs for per-employee KPIs.

    [inputs.period]
        Optional override of the default number of days in the period.

    [ratios]
        Global ratio options (enable/disable, default detail level, etc.).

    [display]
        Display options for the CLI table formatting.

    Notes
    -----
    - The former [paths] section and its `accounting_entries` setting were
      removed in 0.3.0. Data import must now be done explicitly via the CLI
      using the '--import' argument.
    - All file paths in the TOML are resolved relative to the directory of
      the TOML file itself.

    Parameters
    ----------
    path : Path
        Path to the TOML configuration file.

    Returns
    -------
    AppConfig
        Parsed and validated application configuration.
    """
    if config_path is None:
        config_file = Path("smb_finsight_config.toml").resolve()
    else:
        config_file = Path(config_path).resolve()

    raw = _load_toml(config_file)
    base_dir = config_file.parent

    # 1) Fiscal year
    fiscal_year = _parse_fiscal_year(raw)

    # 2) Accounting section
    accounting_section = raw.get("accounting") or {}
    if not isinstance(accounting_section, Mapping):
        accounting_section = {}

    standard = str(accounting_section.get("standard") or "FR_PCG")
    currency = str(accounting_section.get("currency") or "EUR")
    standard_config_path_raw = accounting_section.get("standard_config_file") or None
    if isinstance(standard_config_path_raw, str) and not standard_config_path_raw:
        standard_config_path_raw = None

    standard_config = _parse_standard_config(
        standard=standard,
        standard_config_path_raw=standard_config_path_raw,
        base_dir=base_dir,
    )

    # 3) Database section
    database_section = raw.get("database") or {}
    if not isinstance(database_section, Mapping):
        database_section = {}

    db_engine = str(database_section.get("engine") or "sqlite")
    db_path_raw = database_section.get("path") or "data/db/smb_finsight.sqlite"
    db_path = (base_dir / str(db_path_raw)).resolve()

    database_config = DatabaseConfig(engine=db_engine, path=db_path)

    # 4) Inputs: balance sheet, HR, period
    inputs_section = raw.get("inputs") or {}
    if not isinstance(inputs_section, Mapping):
        inputs_section = {}

    balance_sheet_section = inputs_section.get("balance_sheet") or {}
    if not isinstance(balance_sheet_section, Mapping):
        balance_sheet_section = {}

    hr_section = inputs_section.get("hr") or {}
    if not isinstance(hr_section, Mapping):
        hr_section = {}

    period_section = inputs_section.get("period") or {}
    if not isinstance(period_section, Mapping):
        period_section = {}

    balance_sheet_inputs: dict[str, float] = {}
    for key, value in balance_sheet_section.items():
        try:
            balance_sheet_inputs[str(key)] = float(value)
        except (TypeError, ValueError):
            # Ignore values that cannot be converted to float
            continue

    hr_inputs: dict[str, float] = {}
    for key, value in hr_section.items():
        try:
            hr_inputs[str(key)] = float(value)
        except (TypeError, ValueError):
            # Ignore values that cannot be converted to float
            continue

    # Period inputs: optional override for the period length (in days)
    raw_period_days = period_section.get("period_days")

    if raw_period_days is None:
        # Default: use the actual fiscal year length (inclusive)
        period_days = (fiscal_year.end_date - fiscal_year.start_date).days + 1
    else:
        try:
            period_days = int(raw_period_days)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Invalid value for 'inputs.period.period_days' in the configuration. "
                "Expected an integer."
            ) from exc

    # 5) Ratios options
    ratios_section = raw.get("ratios") or {}
    if not isinstance(ratios_section, Mapping):
        ratios_section = {}

    ratios_enabled = bool(ratios_section.get("enabled", True))
    default_level = str(ratios_section.get("default_level", "basic"))

    # 6) Display options
    display_section = raw.get("display") or {}
    if not isinstance(display_section, Mapping):
        display_section = {}

    display_mode = str(display_section.get("mode", "table"))
    try:
        ratio_decimals = int(display_section.get("ratio_decimals", 1))
    except (TypeError, ValueError):
        ratio_decimals = 1

    return AppConfig(
        fiscal_year=fiscal_year,
        standard=standard,
        currency=currency,
        database=database_config,
        standard_config=standard_config,
        balance_sheet_inputs=balance_sheet_inputs,
        hr_inputs=hr_inputs,
        period_days=period_days,
        ratios_enabled=ratios_enabled,
        default_ratios_level=default_level,
        display_mode=display_mode,
        ratio_decimals=ratio_decimals,
    )
