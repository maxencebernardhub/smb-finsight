# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Period helpers for SMB FinSight.

This module defines a Period value object and helpers to derive
reporting periods (fiscal year, YTD, MTD, last month, last fiscal year)
from the current fiscal year and CLI arguments.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import pandas as pd

from .config import FiscalYear


@dataclass
class Period:
    """Represents a reporting period with a human-readable label."""

    start: date
    end: date
    label: str


def _today() -> date:
    """Return today's date as a date object (isolated for easier testing)."""
    return datetime.today().date()


def period_fy(fy: FiscalYear) -> Period:
    """Full current fiscal year."""
    return Period(
        start=fy.start_date,
        end=fy.end_date,
        label=f"Fiscal year {fy.start_date.year}",
    )


def period_ytd(fy: FiscalYear) -> Period:
    """Year-to-date within the fiscal year."""
    today = _today()
    start = fy.start_date
    end = min(max(today, fy.start_date), fy.end_date)
    return Period(start=start, end=end, label="Year to date")


def period_mtd(fy: FiscalYear) -> Period:
    """Month-to-date within the fiscal year."""
    today = _today()

    # Si today est hors de l'exercice, on retombe sur FY (stratégie simple).
    if today < fy.start_date or today > fy.end_date:
        return period_fy(fy)

    start = today.replace(day=1)
    return Period(start=start, end=today, label="Month to date")


def period_last_month(fy: FiscalYear) -> Period:
    """Full previous calendar month, clamped to the fiscal year if needed."""
    today = _today()

    if today.month == 1:
        year = today.year - 1
        month = 12
    else:
        year = today.year
        month = today.month - 1

    from calendar import monthrange

    start = date(year, month, 1)
    last_day = monthrange(year, month)[1]
    end = date(year, month, last_day)

    # Clamp to fiscal year window
    if end < fy.start_date or start > fy.end_date:
        # Pas de recouvrement → fallback FY
        return period_fy(fy)

    start_clamped = max(start, fy.start_date)
    end_clamped = min(end, fy.end_date)

    return Period(start=start_clamped, end=end_clamped, label="Last month")


def period_last_fy(fy: FiscalYear) -> Period:
    """
    Previous fiscal year.

    For now we assume a simple calendar-like fiscal year for last_fy:
    from 1 Jan of previous year to 31 Dec of previous year.
    This can be refined later if you want arbitrary fiscal-year boundaries.
    """
    prev_year = fy.start_date.year - 1
    return Period(
        start=date(prev_year, 1, 1),
        end=date(prev_year, 12, 31),
        label=f"Previous fiscal year ({prev_year})",
    )


def determine_period_from_args(
    args,
    fy: FiscalYear,
) -> Period:
    """
    Determine the reporting period to use based on CLI args and the fiscal year.

    Priority (highest to lowest):

        1. args.period (fy, ytd, mtd, last-month, last-fy)
        2. args.from_date / args.to_date (custom period)
        3. fiscal year by default
    """
    # 1) Predefined period wins over everything else
    if getattr(args, "period", None):
        p = args.period
        if p == "fy":
            return period_fy(fy)
        if p == "ytd":
            return period_ytd(fy)
        if p == "mtd":
            return period_mtd(fy)
        if p == "last-month":
            return period_last_month(fy)
        if p == "last-fy":
            return period_last_fy(fy)
        raise ValueError(f"Unknown period: {p!r}")

    # 2) Custom from/to dates
    from_raw: Optional[str] = getattr(args, "from_date", None)
    to_raw: Optional[str] = getattr(args, "to_date", None)

    if from_raw or to_raw:
        start = date.fromisoformat(from_raw) if from_raw else fy.start_date
        end = date.fromisoformat(to_raw) if to_raw else fy.end_date

        if end < start:
            raise ValueError("Custom period end date cannot be before start date.")

        label = f"Custom period ({start} → {end})"
        return Period(start=start, end=end, label=label)

    # 3) Default: full fiscal year
    return period_fy(fy)


def filter_entries_by_period(entries: pd.DataFrame, period: Period) -> pd.DataFrame:
    """
    Filter accounting entries DataFrame to keep only entries within the period.

    The `entries` DataFrame is expected to contain a 'date' column of type
    datetime64[ns] (as produced by `read_accounting_entries`).

    Parameters
    ----------
    entries:
        DataFrame with at least a 'date' column.
    period:
        Period defining the [start, end] boundaries (inclusive).

    Returns
    -------
    pandas.DataFrame
        Filtered DataFrame containing only entries within the period.
    """
    mask = (entries["date"] >= pd.Timestamp(period.start)) & (
        entries["date"] <= pd.Timestamp(period.end)
    )
    filtered = entries.loc[mask].copy()
    return filtered
