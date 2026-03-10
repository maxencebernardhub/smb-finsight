# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Preset-based period helpers.

This module provides:
- Period presets used by WebUI (and potentially CLI in the future)
- Granularity splitting (DAY/WEEK/MONTH/QUARTER/CY/FY)

Notes on granularities:
- CY splits into calendar years (YYYY).
- FY splits into fiscal years using fiscal_year.start_date (month/day)
and labels buckets as FY<end_year>.

Presets supported:
- ALL (no time filtering; very wide date span)
- FY, FY_PREV
- YTD, YTD_PREV_FY
- MTD
- LAST_MONTH
- CUSTOM (user-defined period)

Design notes:
- This module is UI-agnostic: WebUI provides the preset string and optionally
  custom_start/custom_end for CUSTOM.
- Period labels can be prefixed when generating sub-periods so that primary and
  comparison series never collide (e.g., "P_2025-01" vs "C_2024-01").
"""

import calendar
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from .config import FiscalYear
from .periods import Period

# ----------------------------
# Types & validation
# ----------------------------


@dataclass(frozen=True)
class CustomRange:
    """User-defined custom range for the CUSTOM preset."""

    start: date
    end: date


class PeriodPresetError(ValueError):
    """Raised when a preset or granularity is invalid."""


# ----------------------------
# Date helpers
# ----------------------------


def _today() -> date:
    # isolated for easier testing/mocking later
    return datetime.today().date()


def _clamp(d: date, min_d: date, max_d: date) -> date:
    return max(min_d, min(d, max_d))


def _shift_year(d: date, years: int) -> date:
    """
    Shift date by a number of years, preserving month/day when possible.
    Handles Feb 29 safely (falls back to Feb 28 on non-leap years).
    """
    try:
        return date(d.year + years, d.month, d.day)
    except ValueError:
        # likely Feb 29 -> Feb 28
        if d.month == 2 and d.day == 29:
            return date(d.year + years, 2, 28)
        raise


def _start_of_month(d: date) -> date:
    return date(d.year, d.month, 1)


def _end_of_month(d: date) -> date:
    if d.month == 12:
        return date(d.year, 12, 31)
    first_next = date(d.year, d.month + 1, 1)
    return first_next - timedelta(days=1)


def _start_of_quarter(d: date) -> date:
    q = (d.month - 1) // 3  # 0..3
    month = q * 3 + 1
    return date(d.year, month, 1)


def _end_of_quarter(d: date) -> date:
    start = _start_of_quarter(d)
    # quarter end is end of month start+2
    month = start.month + 2
    end_month_date = date(start.year, month, 1)
    return _end_of_month(end_month_date)


def _iso_week_label(d: date) -> str:
    iso_year, iso_week, _ = d.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _quarter_label(d: date) -> str:
    q = (d.month - 1) // 3 + 1
    return f"{d.year}-Q{q}"


# ----------------------------
# Presets -> Period
# ----------------------------


def period_from_preset(
    preset: str,
    fy: FiscalYear,
    *,
    as_of: date | None = None,
    custom: CustomRange | None = None,
    label: str | None = None,
    user_presets: Mapping[str, Mapping[str, str]] | None = None,
) -> Period:
    """
    Build a Period from a preset string.

    Parameters
    ----------
    preset:
        One of: ALL, FY, FY_PREV, YTD, YTD_PREV_FY, MTD, LAST_MONTH, CUSTOM
    fy:
        Current fiscal year boundaries.
    as_of:
        Reference date (defaults to today). Used to compute YTD/MTD/LAST_MONTH.
        Note: LAST_MONTH returns the previous *calendar* month
        and may cross FY boundaries.
    custom:
        Required when preset=CUSTOM (user-defined range).
    label:
        Optional label override. If not provided, a standard label is used.
    user_presets:
        Optional mapping for user-defined presets (e.g., from layout TOML).
        Each preset must define ISO dates: {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}.


    Returns
    -------
    Period
    """
    p = (preset or "").strip().upper()
    today = as_of or _today()

    # User-defined presets (from layout_en.toml)
    if user_presets and p in user_presets:
        tbl = user_presets[p]
        start = date.fromisoformat(str(tbl["start"]))
        end = date.fromisoformat(str(tbl["end"]))
        return Period(start=start, end=end, label=label or p)

    # Helper: current FY "as-of" date clamped inside FY
    today_in_fy = _clamp(today, fy.start_date, fy.end_date)

    if p == "ALL":
        # "All periods" means no date filtering in the UI.
        # We model it as a very wide span so downstream code can keep using Period.
        return Period(
            start=date(1900, 1, 1),
            end=date(9999, 12, 31),
            label=label or "ALL",
        )

    if p == "FY":
        return Period(start=fy.start_date, end=fy.end_date, label=label or "FY")

    if p == "FY_PREV":
        prev_start = _shift_year(fy.start_date, -1)
        prev_end = _shift_year(fy.end_date, -1)
        return Period(start=prev_start, end=prev_end, label=label or "FY_PREV")

    if p == "YTD":
        return Period(start=fy.start_date, end=today_in_fy, label=label or "YTD")

    if p == "YTD_PREV_FY":
        prev_start = _shift_year(fy.start_date, -1)
        prev_end = _shift_year(fy.end_date, -1)
        # align "as-of" inside previous FY
        prev_as_of = _shift_year(today_in_fy, -1)
        prev_as_of = _clamp(prev_as_of, prev_start, prev_end)
        return Period(start=prev_start, end=prev_as_of, label=label or "YTD_PREV_FY")

    if p == "MTD":
        # month-to-date, clamped inside FY
        m_start = _start_of_month(today_in_fy)
        m_end = today_in_fy
        # clamp to FY (handles FY not matching calendar year)
        m_start = _clamp(m_start, fy.start_date, fy.end_date)
        m_end = _clamp(m_end, fy.start_date, fy.end_date)
        return Period(start=m_start, end=m_end, label=label or "MTD")

    if p == "LAST_MONTH":
        # previous calendar month (NOT clamped to FY: it can cross FY boundaries)
        first_this_month = _start_of_month(today)
        last_day_prev_month = first_this_month - timedelta(days=1)
        lm_start = _start_of_month(last_day_prev_month)
        lm_end = _end_of_month(last_day_prev_month)
        return Period(start=lm_start, end=lm_end, label=label or "LAST_MONTH")

    if p == "CUSTOM":
        if custom is None:
            raise PeriodPresetError(
                "CUSTOM preset requires a CustomRange (custom=...)."
            )
        if custom.end < custom.start:
            raise PeriodPresetError("CUSTOM range is invalid: end < start.")
        return Period(start=custom.start, end=custom.end, label=label or "CUSTOM")

    raise PeriodPresetError(f"Unknown preset: {preset!r}")


def _is_full_month_span(start: date, end: date) -> bool:
    """Return True if [start, end] covers whole months only."""
    if start.day != 1:
        return False
    last_day = calendar.monthrange(end.year, end.month)[1]
    return end.day == last_day


def _add_months(d: date, months: int) -> date:
    """Add months to a date, clamping day to month length."""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    last_day = calendar.monthrange(y, m)[1]
    day = min(d.day, last_day)
    return date(y, m, day)


# Similar to _shift_year, but implemented via date.replace() for relative presets.
def _shift_year_safe(d: date, years: int) -> date:
    """Shift year keeping month/day when possible; clamp Feb 29 to Feb 28."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        # e.g. Feb 29 -> Feb 28
        return d.replace(year=d.year + years, day=28)


def period_from_relative_preset(
    preset: str,
    reference: Period,
    *,
    label: str | None = None,
) -> Period:
    """
    Build a Period relative to an existing one (reference).
    Supported presets:
        - PREV_PERIOD: immediately preceding period of same duration.
        - SAME_PERIOD_PREV_FY: same calendar period shifted by -1 year.
    """
    p = preset.strip().upper()

    if p == "SAME_PERIOD_PREV_FY":
        return Period(
            start=_shift_year_safe(reference.start, -1),
            end=_shift_year_safe(reference.end, -1),
            label=label or p,
        )

    if p == "PREV_PERIOD":
        # If the reference spans full months, preserve whole-month span.
        if _is_full_month_span(reference.start, reference.end):
            # number of months covered (inclusive)
            months = (
                (reference.end.year - reference.start.year) * 12
                + (reference.end.month - reference.start.month)
                + 1
            )
            prev_end_month = _add_months(reference.start, -1)
            prev_end_last_day = calendar.monthrange(
                prev_end_month.year, prev_end_month.month
            )[1]
            prev_end = date(
                prev_end_month.year, prev_end_month.month, prev_end_last_day
            )

            # start = first day of month (months-1) months before prev_end
            prev_start_month = _add_months(
                date(prev_end.year, prev_end.month, 1), -(months - 1)
            )
            prev_start = date(prev_start_month.year, prev_start_month.month, 1)

            return Period(start=prev_start, end=prev_end, label=label or p)

        # Otherwise: same number of days
        duration_days = (reference.end - reference.start).days
        prev_end = reference.start - timedelta(days=1)
        prev_end = date(prev_end.year, prev_end.month, prev_end.day)
        prev_start = prev_end - timedelta(days=duration_days)
        prev_start = date(prev_start.year, prev_start.month, prev_start.day)

        return Period(start=prev_start, end=prev_end, label=label or p)

    raise PeriodPresetError(f"Unknown relative preset: {preset!r}")


# ----------------------------
# Granularity splitting
# ----------------------------


def split_period(
    period: Period,
    granularity: str,
    *,
    label_prefix: str = "",
    fiscal_year: Any | None = None,
) -> list[Period]:
    """
    Split a Period into sub-periods based on granularity.

    Granularities:
    - DAY: daily buckets
    - WEEK: ISO weeks (Mon..Sun)
    - MONTH: calendar months
    - QUARTER: calendar quarters
    - CY: calendar years labeled "YYYY"
    - FY: fiscal years computed from fiscal_year.start_date (month/day),
    labeled "FY<end_year>"

    Labels are stable and sortable. Example for MONTH:
    - 2025-01, 2025-02, ...
    With prefix: P_2025-01, C_2024-01, ...
    """
    g = (granularity or "").strip().upper()
    if g not in {"DAY", "WEEK", "MONTH", "QUARTER", "CY", "FY"}:
        raise PeriodPresetError(f"Unknown granularity: {granularity!r}")

    buckets: list[Period] = []

    if g == "CY":
        # Split by calendar year (calendar-year buckets).
        year = period.start.year
        while year <= period.end.year:
            y_start = date(year, 1, 1)
            y_end = date(year, 12, 31)
            start = max(period.start, y_start)
            end = min(period.end, y_end)
            if start <= end:
                lbl = f"{year}"
                buckets.append(
                    Period(start=start, end=end, label=f"{label_prefix}{lbl}")
                )
            year += 1
        return buckets

    if g == "FY":
        if fiscal_year is None:
            raise PeriodPresetError("split_period(FY) requires fiscal_year=...")

        fy_start_month = fiscal_year.start_date.month
        fy_start_day = fiscal_year.start_date.day

        def _fy_start_for(d: date) -> date:
            """Fiscal-year start date for the FY that contains date d."""
            candidate = date(d.year, fy_start_month, fy_start_day)
            return (
                candidate
                if d >= candidate
                else date(d.year - 1, fy_start_month, fy_start_day)
            )

        cur = period.start

        while cur <= period.end:
            fy_start = _fy_start_for(cur)
            fy_next_start = date(fy_start.year + 1, fy_start_month, fy_start_day)
            fy_end = fy_next_start - timedelta(days=1)

            b_start = max(period.start, fy_start)
            b_end = min(period.end, fy_end)

            # Convention: FY label by end year (common in finance)
            label = f"FY{fy_end.year}"
            buckets.append(
                Period(start=b_start, end=b_end, label=f"{label_prefix}{label}")
            )

            cur = fy_end + timedelta(days=1)

        return buckets

    if g == "DAY":
        cur = period.start
        while cur <= period.end:
            lbl = cur.isoformat()
            buckets.append(Period(start=cur, end=cur, label=f"{label_prefix}{lbl}"))
            cur += timedelta(days=1)
        return buckets

    if g == "WEEK":
        # bucket weeks as ISO weeks; each bucket is Monday..Sunday clipped to period
        # bounds
        cur = period.start
        while cur <= period.end:
            # move to monday of that week
            monday = cur - timedelta(days=cur.weekday())
            sunday = monday + timedelta(days=6)
            start = max(period.start, monday)
            end = min(period.end, sunday)
            lbl = _iso_week_label(cur)
            buckets.append(Period(start=start, end=end, label=f"{label_prefix}{lbl}"))
            cur = sunday + timedelta(days=1)
        # Defensive: if boundaries create repeated ISO week labels,
        # merge same-label buckets.

        return _merge_same_label(buckets)

    if g == "MONTH":
        cur = period.start
        while cur <= period.end:
            m_start = _start_of_month(cur)
            m_end = _end_of_month(cur)
            start = max(period.start, m_start)
            end = min(period.end, m_end)
            lbl = f"{cur.year}-{cur.month:02d}"
            buckets.append(Period(start=start, end=end, label=f"{label_prefix}{lbl}"))
            cur = m_end + timedelta(days=1)
        return _merge_same_label(buckets)

    if g == "QUARTER":
        cur = period.start
        while cur <= period.end:
            q_start = _start_of_quarter(cur)
            q_end = _end_of_quarter(cur)
            start = max(period.start, q_start)
            end = min(period.end, q_end)
            lbl = _quarter_label(cur)
            buckets.append(Period(start=start, end=end, label=f"{label_prefix}{lbl}"))
            cur = q_end + timedelta(days=1)
        return _merge_same_label(buckets)

    # unreachable
    return buckets


def _merge_same_label(periods: list[Period]) -> list[Period]:
    """
    Merge consecutive periods with the same label (defensive for week/month loops).
    Assumes periods are generated in chronological order.
    """
    if not periods:
        return periods
    merged: list[Period] = []
    cur = periods[0]
    for p in periods[1:]:
        if p.label == cur.label:
            cur = Period(start=cur.start, end=max(cur.end, p.end), label=cur.label)
        else:
            merged.append(cur)
            cur = p
    merged.append(cur)
    return merged
