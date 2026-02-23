# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Formatting helpers for WebUI.

This module centralizes formatting and delta rendering logic for Streamlit components
(tiles, tables, charts annotations).

Key goals:
- Produce stable human-readable strings for amounts, percentages, days,
and plain numbers.
- Prevent UI artifacts such as "nan" leaking into the dashboard.
- Build Streamlit-compatible delta strings:
  Streamlit parses the delta sign to decide arrow direction and color, so we must use
  ASCII "-" for negatives (not the Unicode minus "−").

Finance conventions:
- Percent values are represented internally as fractions (0.04 -> 4%).
- Percent-point deltas (pp) are used for abs-only deltas on percent tiles
  (e.g. 4% -> 3% => -1.00 pp).
"""

import math
from typing import Optional


# Treat NaN as missing value to prevent "nan" leaking into UI strings.
def _is_nan(x: object) -> bool:
    try:
        return isinstance(x, (int, float)) and math.isnan(float(x))
    except Exception:
        return False


def _format_number(value: float, *, decimals: int, thousands_separator: str) -> str:
    """Format number with a configurable thousands separator (',' or ' ')."""
    s = f"{value:,.{decimals}f}"  # uses ',' as thousands sep by default
    if thousands_separator == " ":
        s = s.replace(",", " ")
    return s


def _format_currency(
    value: float, *, currency_code: str, thousands_separator: str
) -> str:
    """Format currency for CAD/USD/EUR.

    - CAD/USD: "$" prefix
    - EUR: "€" suffix with a space (French-style positioning)
    """
    amount = _format_number(value, decimals=2, thousands_separator=thousands_separator)

    code = (currency_code or "CAD").upper().strip()
    if code == "EUR":
        return f"{amount} €"
    # CAD or USD -> $ prefix
    return f"${amount}"


def _fmt_value(
    value: Optional[float],
    fmt: str,
    *,
    currency_code: str,
    thousands_separator: str,
) -> str:
    """
    Format a numeric value for display.

    Args:
        value: Numeric value (or None).
        fmt: Display format. Common values:
            - "amount": currency (value in base currency units)
            - "percent": percentage (value is a fraction, e.g. 0.042 -> 4.20%)
            - "ratio": ratio
            - "number": generic number with separators
        currency_code: Currency code prefix/suffix used for "amount".
        thousands_separator: "," or " " (space), applied to formatted numbers.

    Returns:
        A display string. For missing values (None/NaN),
        returns a safe placeholder (e.g. "—").
    """

    if value is None or _is_nan(value):
        return "—"

    f = (fmt or "").lower().strip()

    if f in {"currency", "money", "amount"}:
        return _format_currency(
            value,
            currency_code=currency_code,
            thousands_separator=thousands_separator,
        )

    if f in {"number", "int"}:
        return f"{value:,.0f}"
    if f in {"float"}:
        return f"{value:,.2f}"
    if f in {"percent", "%"}:
        return f"{value * 100:,.2f}%"
    if f in {"ratio"}:
        return f"{value:,.2f}"

    # fallback: try a reasonable default
    return f"{value:,.2f}"


# IMPORTANT: Streamlit `st.metric` determines delta arrow/color by parsing the sign.
# Use ASCII "-" for negative values; Unicode minus "−" may be treated as non-negative.
def _sign_str(x: float) -> str:
    if x > 0:
        return "+"
    if x < 0:
        return "-"  # ASCII minus (Streamlit recognizes it)
    return ""


def _format_pp(delta_fraction: float, *, thousands_separator: str) -> str:
    """
    Format a delta expressed as a fraction into percentage points (pp).

    Example:
      delta_fraction = -0.01  -> "-1.00 pp"
      delta_fraction = 0.260729 -> "+26.07 pp"
    """
    value = abs(delta_fraction) * 100.0
    s = f"{value:,.2f}"
    if thousands_separator == " ":
        s = s.replace(",", " ")
    return f"{_sign_str(delta_fraction)}{s} pp"


def _build_delta_string(
    *,
    delta_abs: Optional[float],
    delta_pct: Optional[float],
    fmt: str,
    show_abs: bool,
    show_pct: bool,
    currency_code: str,
    thousands_separator: str,
) -> Optional[str]:
    """
    Build a single Streamlit-compatible delta string.

    Streamlit `st.metric` accepts only one delta string. This helper can combine
    absolute and relative deltas, e.g. "+$120 ( +5.2% )" depending on flags.

    Args:
        delta_abs: Absolute delta (primary - comparison).
        delta_pct: Relative delta as a fraction (e.g. 0.052 -> +5.2%).
        fmt: Formatting mode ("amount", "percent", "days", "number", ...).
        show_abs/show_pct: Whether to include each component.
        currency_code/thousands_separator: Formatting options.

    Returns:
        A delta string or None if nothing should be displayed.
    """
    if (delta_abs is None and delta_pct is None) or (not show_abs and not show_pct):
        return None

    parts: list[str] = []

    if show_abs and delta_abs is not None:
        abs_fmt = _fmt_value(
            abs(delta_abs),
            fmt,
            currency_code=currency_code,
            thousands_separator=thousands_separator,
        )

        parts.append(f"{_sign_str(delta_abs)}{abs_fmt}")

    if show_pct and delta_pct is not None:
        pct_fmt = _fmt_value(
            abs(delta_pct),
            "percent",
            currency_code=currency_code,
            thousands_separator=thousands_separator,
        )

        pct_part = f"{_sign_str(delta_pct)}{pct_fmt}"

        if show_abs and delta_abs is not None:
            parts.append(f"({pct_part})")
        else:
            parts.append(pct_part)

    if not parts:
        return None
    return " ".join(parts)


def _compute_delta(
    primary: Optional[float], comp: Optional[float]
) -> tuple[Optional[float], Optional[float]]:
    """
    Compute deltas between primary and comparison values.

    Returns:
        delta_abs: primary_val - comp_val
        delta_pct: relative change as a fraction: delta_abs / abs(comp_val)
                  (i.e., -0.10 means -10% relative to comparison)

    Notes:
        - If comp_val is 0 or missing, delta_pct is None to avoid division errors.
        - Percent-point deltas (pp) are handled separately in `_format_pp`.
    """

    if primary is None or comp is None or _is_nan(primary) or _is_nan(comp):
        return None, None
    delta_abs = primary - comp
    if comp == 0:
        delta_pct = None
    else:
        delta_pct = delta_abs / abs(comp)
    return delta_abs, delta_pct
