# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
WebUI data access helpers.

This module centralizes lookup logic for values and notes stored in the multi-period
outputs produced by `compute_all_multi_period()`.

Expected DataFrame conventions:
- measures_df and ratios_df contain multiple periods identified
by a `period_label` column.
  Common values include "PRIMARY", "COMPARISON", and bucket labels
  such as "P_YYYY-MM" / "C_YYYY-MM" depending on the page pipeline.
- Each measure/ratio is identified by a `key` column.
- Numeric values are stored in a `value` column.
- Optional human-readable notes may be stored in a `notes` column.

All helpers are defensive:
- They return `None` when a value cannot be found or is not usable.
- They return "" (empty string) for missing notes.
"""

from typing import Any, Optional

import pandas as pd


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _measure_value(
    measures_df: pd.DataFrame, period_label: str, key: str
) -> Optional[float]:
    """
    Return the numeric measure value for a given period and key.

    Args:
        measures_df: Multi-period measures DataFrame.
        period_label: Label identifying the period
        (e.g. "PRIMARY", "COMPARISON", "P_2025-01").
        key: Canonical measure key.

    Returns:
        The value as float, or None if not found / not parseable / NaN.
    """

    if measures_df is None or measures_df.empty:
        return None
    rows = measures_df[
        (measures_df["period_label"] == period_label)
        & (measures_df["measure_key"] == key)
    ]
    if rows.empty:
        return None
    return _safe_float(rows.iloc[0]["value"])


def _ratio_value(
    ratios_df: pd.DataFrame, period_label: str, key: str
) -> Optional[float]:
    """
    Return the numeric ratio value for a given period and key.

    Returns:
        The value as float, or None if not found / not parseable / NaN.
    """
    if ratios_df is None or ratios_df.empty:
        return None
    rows = ratios_df[
        (ratios_df["period_label"] == period_label) & (ratios_df["key"] == key)
    ]
    if rows.empty:
        return None
    return _safe_float(rows.iloc[0]["value"])


def _measure_notes(measures_df: pd.DataFrame, key: str) -> str:
    """
    Return notes for a measure key, if present.

    Notes are not period-specific in the current WebUI: the first available notes
    for a given key are returned.

    Returns:
        Notes string or "" if missing.
    """
    if measures_df is None or measures_df.empty or not key:
        return ""
    rows = measures_df[measures_df["measure_key"] == key]
    if rows.empty:
        return ""
    # Notes are repeated per period; pick the first non-empty string.
    for v in rows["notes"].tolist():
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _ratio_notes(ratios_df: pd.DataFrame, key: str) -> str:
    """
    Return notes for a ratio key, if present.

    Notes are not period-specific in the current WebUI: the first available notes
    for a given key are returned.

    Returns:
        Notes string or "" if missing.
    """
    if ratios_df is None or ratios_df.empty or not key:
        return ""
    rows = ratios_df[ratios_df["key"] == key]
    if rows.empty:
        return ""
    for v in rows["notes"].tolist():
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""
