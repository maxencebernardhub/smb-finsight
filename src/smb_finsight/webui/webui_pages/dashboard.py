# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Dashboard page (WebUI).

Design (v0.5.0):
- The *page-level* period settings drive ALL tiles and charts.
- No per-tile / per-chart overrides (by choice for simplicity).
- Period presets are configurable via layout TOML
(including optional user-defined presets).
- Tiles may show tooltips sourced from measure/ratio notes (when available).
- Delta display supports abs/pct and uses delta_good_direction to
set Streamlit delta_color.

Charts visualization (single-chart container):
- If comparison is disabled: a single chart is rendered (Streamlit native).
- If comparison is enabled: the rendering mode is selected automatically via
  decide_chart_render_mode() based on:
  - primary/comparison preset codes,
  - granularity,
  - number of buckets (sub-periods).

Possible rendering modes:
- "side_by_side_streamlit": 2 charts side-by-side (Primary | Comparison).
- "aligned_altair": a single Altair chart where primary/comparison series share
the same aligned x-axis.
- "indexed_altair": a single Altair chart where x-axis is reindexed (D01/W01/M01...)
to compare shapes.
"""

import calendar
from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any, Literal, Optional

import altair as alt
import pandas as pd
import streamlit as st

from smb_finsight.config import AppConfig
from smb_finsight.multi_periods import compute_all_multi_period
from smb_finsight.period_utils import (
    CustomRange,
    period_from_preset,
    period_from_relative_preset,
    split_period,
)
from smb_finsight.webui.layout import LayoutConfig, PageConfig

# -----------------------------------------------------------------------------
# Small helpers (robust to dataclass OR dict configs)
# -----------------------------------------------------------------------------


def _to_mapping(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if is_dataclass(obj):
        return asdict(obj)
    return {k: getattr(obj, k) for k in dir(obj) if not k.startswith("_")}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return list(value)


# -----------------------------------------------------------------------------
# Formatting helpers
# -----------------------------------------------------------------------------


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _fmt_value(value: Optional[float], fmt: str, *, currency_symbol: str = "$") -> str:
    if value is None:
        return "—"

    f = (fmt or "").lower().strip()

    if f in {"currency", "money", "amount"}:
        return f"{currency_symbol}{value:,.2f}"
    if f in {"number", "int"}:
        return f"{value:,.0f}"
    if f in {"float"}:
        return f"{value:,.2f}"
    if f in {"percent", "%"}:
        return f"{value * 100:,.2f}%"
    if f in {"ratio"}:
        return f"{value:,.2f}"

    return f"{value:,.2f}"


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
    if value is None:
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


def _sign_str(x: float) -> str:
    if x > 0:
        return "+"
    if x < 0:
        return "-"
    return ""


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
    Return a single delta string for st.metric (abs and/or pct).

    Rules:
    - If show_abs: include signed absolute delta formatted according to fmt.
    - If show_pct: include signed percentage delta
    (2 decimals as configured by _fmt_value).
    - If both are enabled: returns "<abs> (<pct>)".
    Note: Delta coloring is handled by st.metric(delta_color=...) based on
    delta_good_direction.
    """

    if (delta_abs is None and delta_pct is None) or (not show_abs and not show_pct):
        return None

    parts: list[str] = []

    if show_abs and delta_abs is not None:
        parts.append(
            f"{_sign_str(delta_abs)}"
            f"{
                _fmt_value(
                    abs(delta_abs),
                    fmt,
                    currency_code=currency_code,
                    thousands_separator=thousands_separator,
                )
            }"
        )

    if show_pct and delta_pct is not None:
        pct_part = (
            f"{_sign_str(delta_pct)}"
            f"{
                _fmt_value(
                    abs(delta_pct),
                    'percent',
                    currency_code=currency_code,
                    thousands_separator=thousands_separator,
                )
            }"
        )
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
    if primary is None or comp is None:
        return None, None
    delta_abs = primary - comp
    if comp == 0:
        delta_pct = None
    else:
        delta_pct = delta_abs / abs(comp)
    return delta_abs, delta_pct


# -----------------------------------------------------------------------------
# Data extraction from MultiPeriod outputs
# -----------------------------------------------------------------------------


def _measure_value(
    measures_df: pd.DataFrame, period_label: str, key: str
) -> Optional[float]:
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
    if ratios_df is None or ratios_df.empty:
        return None
    rows = ratios_df[
        (ratios_df["period_label"] == period_label) & (ratios_df["key"] == key)
    ]
    if rows.empty:
        return None
    return _safe_float(rows.iloc[0]["value"])


def _measure_notes(measures_df: pd.DataFrame, key: str) -> str:
    """Return notes for a given measure_key (if any)."""
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
    """Return notes for a given ratio key (if any)."""
    if ratios_df is None or ratios_df.empty or not key:
        return ""
    rows = ratios_df[ratios_df["key"] == key]
    if rows.empty:
        return ""
    for v in rows["notes"].tolist():
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _build_chart_df(
    *,
    measures_df: pd.DataFrame,
    ratios_df: pd.DataFrame,
    period_labels: list[str],
    series: list[dict[str, Any]],
    label_prefix: str,
) -> pd.DataFrame:
    if (measures_df is None or measures_df.empty) and (
        ratios_df is None or ratios_df.empty
    ):
        return pd.DataFrame()
    if not period_labels:
        return pd.DataFrame()

    bucket_index = [
        lbl[len(label_prefix) :] if lbl.startswith(label_prefix) else lbl
        for lbl in period_labels
    ]
    out = pd.DataFrame(index=bucket_index)

    for s in series:
        source = (s.get("source") or "measure").lower()
        key = s.get("key")
        label = s.get("label") or key

        if not key:
            continue

        values: list[Optional[float]] = []
        for pl in period_labels:
            if source == "ratio":
                values.append(_ratio_value(ratios_df, pl, key))
            else:
                values.append(_measure_value(measures_df, pl, key))

        out[label] = values

    return out


# -----------------------------------------------------------------------------
# Charts helpers
# -----------------------------------------------------------------------------

ChartRenderMode = Literal["single", "side_by_side", "aligned_altair", "indexed_altair"]


_ALIGNED_KNOWN_PAIRS: set[tuple[str, str]] = {
    ("FY", "FY_PREV"),
    ("FY", "SAME_PERIOD_PREV_FY"),
    ("YTD", "YTD_PREV_FY"),
    ("YTD", "SAME_PERIOD_PREV_FY"),
    ("MTD", "SAME_PERIOD_PREV_FY"),
}

_INDEXED_KNOWN_PAIRS: set[tuple[str, str]] = {
    ("MTD", "SAME_PERIOD_PREV_FY"),
}


def _is_full_month_span(start: date, end: date) -> bool:
    """True if [start, end] covers whole months only (start=1st, end=last day)."""
    if start.day != 1:
        return False
    last_day = calendar.monthrange(end.year, end.month)[1]
    return end.day == last_day


def _months_span_count(start: date, end: date) -> int:
    """Number of months covered by [start, end] assuming full-month span."""
    return (end.year - start.year) * 12 + (end.month - start.month) + 1


def decide_chart_render_mode(
    *,
    comparison_enabled: bool,
    granularity: str,
    primary_preset: str,
    comparison_preset: str | None,
    primary_period: Any,
    comparison_period: Any | None,
    primary_buckets: list[Any],
    comp_buckets: list[Any],
) -> ChartRenderMode:
    """
    Decide how to render a chart when comparison is enabled.

    The decision is based on:
    - preset codes (primary/comparison),
    - granularity,
    - number of buckets (primary and comparison).

    Returns a mode among:
    - "side_by_side_streamlit"
    - "aligned_altair"
    - "indexed_altair"
    """

    if not comparison_enabled or comparison_period is None or not comparison_preset:
        return "single"

    g = (granularity or "").upper()
    p1 = (primary_preset or "").upper()
    p2 = (comparison_preset or "").upper()

    # If we can't even split properly, safest is side-by-side
    if not primary_buckets or not comp_buckets:
        return "side_by_side"

    # FY: one point most of the time; keep it simple
    if g == "FY":
        return "side_by_side"

    # MONTH / QUARTER -> try aligned
    if g in {"MONTH", "QUARTER"}:
        same_bucket_len = len(primary_buckets) == len(comp_buckets)

        # If there is only 1 bucket, aligned overlay is not useful → prefer side-by-side
        if len(primary_buckets) <= 1 or len(comp_buckets) <= 1:
            return "side_by_side"

        if (p1, p2) in _ALIGNED_KNOWN_PAIRS and same_bucket_len:
            return "aligned_altair"

        # CUSTOM alignment heuristic: full-month spans + same number of months
        if p1 == "CUSTOM" and p2 == "CUSTOM":
            p_full_month = _is_full_month_span(primary_period.start, primary_period.end)
            c_full_month = _is_full_month_span(
                comparison_period.start, comparison_period.end
            )
            if p_full_month and c_full_month:
                p_months = _months_span_count(primary_period.start, primary_period.end)
                c_months = _months_span_count(
                    comparison_period.start, comparison_period.end
                )
                if p_months == c_months and same_bucket_len:
                    return "aligned_altair"

        return "side_by_side"

    # DAY / WEEK -> prefer indexed when same length
    if g in {"DAY", "WEEK"}:
        if len(primary_buckets) == len(comp_buckets):
            return "indexed_altair"
        if (p1, p2) in _INDEXED_KNOWN_PAIRS:
            return "indexed_altair"
        return "side_by_side"

    return "side_by_side"


def _wide_to_long(
    df_wide: pd.DataFrame, *, period_kind: str, bucket_order: list[str]
) -> pd.DataFrame:
    """Convert wide DF (index=bucket, cols=series) to long DF for Altair."""
    if df_wide is None or df_wide.empty:
        return pd.DataFrame(columns=["bucket", "series", "value", "period_kind"])

    out = df_wide.reset_index().rename(columns={"index": "bucket"})
    long_df = out.melt(id_vars=["bucket"], var_name="series", value_name="value")
    long_df["period_kind"] = period_kind
    long_df["bucket"] = pd.Categorical(
        long_df["bucket"], categories=bucket_order, ordered=True
    )
    return long_df


def _make_index_labels(n: int, granularity: str) -> list[str]:
    """D01.. / W01.. index labels for indexed comparison charts."""
    g = (granularity or "").upper()
    prefix = "W" if g == "WEEK" else "D"
    return [f"{prefix}{i:02d}" for i in range(1, n + 1)]


def _render_altair_lines(
    df_long: pd.DataFrame,
    *,
    title: str,
    indexed: bool,
) -> None:
    """
    Render an Altair line chart from a long dataframe.

    Expected df_long columns:
    - bucket (str)
    - bucket_order (int) used to enforce axis ordering
    - series (str)
    - value (float)
    - period_kind ("Primary" / "Comparison")
    """

    if df_long is None or df_long.empty:
        st.info("No data.")
        return

    base = alt.Chart(df_long).encode(
        x=alt.X(
            "bucket:N",
            sort=None if indexed else None,  # keep order as provided
            title=None,
        ),
        y=alt.Y("value:Q", title=None),
        color=alt.Color("series:N", title=None),
        tooltip=[
            alt.Tooltip("period_kind:N", title="Period"),
            alt.Tooltip("bucket:N", title="Bucket"),
            alt.Tooltip("series:N", title="Series"),
            alt.Tooltip("value:Q", title="Value"),
        ],
    )

    # Solid for primary, dashed for comparison
    line = base.mark_line(point=False).encode(
        strokeDash=alt.StrokeDash(
            "period_kind:N",
            sort=["Primary", "Comparison"],
            scale=alt.Scale(domain=["Primary", "Comparison"], range=[[1, 0], [6, 4]]),
            legend=alt.Legend(title=None),
        )
    )

    st.altair_chart(line.interactive(), width="stretch")


def _render_chart(
    *,
    mode: ChartRenderMode,
    kind: str,
    title: str,
    granularity: str,
    primary_label: str,
    comparison_label: str | None,
    # Wide DFs already built for primary/comparison:
    primary_df: pd.DataFrame,
    comparison_df: pd.DataFrame | None,
) -> None:
    """
    Render a chart according to decided mode.

    - single: Streamlit native chart, full width
    - side_by_side: Streamlit native charts in 2 columns (Primary | Comparison)
    - aligned_altair: one Altair chart with overlapping buckets (months/quarters)
    - indexed_altair: one Altair chart with D01/W01 axis (days/weeks)
    """
    k = (kind or "line").lower()

    # Auto bar override: 1 point -> bar is clearer than line
    def _should_bar(df: pd.DataFrame) -> bool:
        return df is not None and not df.empty and len(df.index) <= 1

    if mode == "single":
        if primary_df is None or primary_df.empty:
            st.info("No data.")
            return
        if k == "bar" or _should_bar(primary_df):
            st.bar_chart(primary_df)
        else:
            st.line_chart(primary_df)
        return

    if mode == "side_by_side":
        left, right = st.columns(2)

        with left:
            st.caption(f"{primary_label}")
            if primary_df is None or primary_df.empty:
                st.info("No data.")
            else:
                if k == "bar" or _should_bar(primary_df):
                    st.bar_chart(primary_df)
                else:
                    st.line_chart(primary_df)

        with right:
            st.caption(f"{comparison_label}")
            if comparison_df is None or comparison_df.empty:
                st.info("No data.")
            else:
                if k == "bar" or _should_bar(comparison_df):
                    st.bar_chart(comparison_df)
                else:
                    st.line_chart(comparison_df)

        return

    # Altair modes
    if comparison_df is None or comparison_df.empty:
        # if no comp data, fallback to single
        if primary_df is None or primary_df.empty:
            st.info("No data.")
            return
        if k == "bar" or _should_bar(primary_df):
            st.bar_chart(primary_df)
        else:
            st.line_chart(primary_df)
        return

    if mode == "indexed_altair":
        # Replace bucket labels with D01/W01… based on row order
        n = max(len(primary_df.index), len(comparison_df.index))
        idx_labels = _make_index_labels(n, granularity)

        p = primary_df.copy()
        c = comparison_df.copy()
        p.index = idx_labels[: len(p.index)]
        c.index = idx_labels[: len(c.index)]

        bucket_order = idx_labels
        df_long = pd.concat(
            [
                _wide_to_long(p, period_kind="Primary", bucket_order=bucket_order),
                _wide_to_long(c, period_kind="Comparison", bucket_order=bucket_order),
            ],
            ignore_index=True,
        )
        _render_altair_lines(df_long, title=title, indexed=True)
        return

    if mode == "aligned_altair":
        # Keep bucket labels as-is (e.g. Jan..Dec or Q1..Q4)
        bucket_order = list(primary_df.index)
        df_long = pd.concat(
            [
                _wide_to_long(
                    primary_df, period_kind="Primary", bucket_order=bucket_order
                ),
                _wide_to_long(
                    comparison_df, period_kind="Comparison", bucket_order=bucket_order
                ),
            ],
            ignore_index=True,
        )
        _render_altair_lines(df_long, title=title, indexed=False)
        return


# -----------------------------------------------------------------------------
# Custom range validation helper
# -----------------------------------------------------------------------------


def _validate_custom_range(
    start: Optional[date],
    end: Optional[date],
    *,
    toast: bool,
    error_message: str,
) -> bool:
    if start is None or end is None:
        return False
    if end < start:
        st.warning(error_message)
        if toast:
            st.toast(error_message, icon="⚠️")
        st.stop()
        return False
    return True


# -----------------------------------------------------------------------------
# Charts rendering helpers
# -----------------------------------------------------------------------------


def _aligned_bucket_labels(buckets: list[Any], granularity: str) -> list[str]:
    """Return aligned labels for MONTH/QUARTER buckets (Jan..Dec / Q1..Q4)."""
    g = (granularity or "").upper()

    if g == "MONTH":
        # Use English month abbreviations (can be localized later via TOML if needed)
        months = [
            "Jan",
            "Feb",
            "Mar",
            "Apr",
            "May",
            "Jun",
            "Jul",
            "Aug",
            "Sep",
            "Oct",
            "Nov",
            "Dec",
        ]
        out: list[str] = []
        for b in buckets:
            m = int(b.start.month)
            out.append(months[m - 1])
        return out

    if g == "QUARTER":
        out = []
        for b in buckets:
            m = int(b.start.month)
            q = (m - 1) // 3 + 1
            out.append(f"Q{q}")
        return out

    # fallback: keep current labels
    return [str(getattr(b, "label", "")) for b in buckets]


def _render_single_or_side_by_side_chart(
    *,
    title: str,
    kind: str,
    measures_df: pd.DataFrame,
    ratios_df: pd.DataFrame,
    granularity: str,
    primary_preset_code: str,
    comparison_preset_code: str | None,
    primary_period: Any,
    comparison_period: Any | None,
    primary_buckets: list[Any],
    comp_buckets: list[Any],
    series: list[dict[str, Any]],
    comparison_enabled: bool,
    primary_preset_label: str,
    comparison_preset_label: str,
) -> None:
    st.markdown(f"###### {title}")

    # Build primary dataframe
    p_labels = [p.label for p in primary_buckets]
    p_df = _build_chart_df(
        measures_df=measures_df,
        ratios_df=ratios_df,
        period_labels=p_labels,
        series=series,
        label_prefix="P_",
    )

    # Build comparison dataframe (if enabled)
    c_df: pd.DataFrame | None = None
    if comparison_enabled and comparison_period is not None and comparison_preset_code:
        c_labels = [p.label for p in comp_buckets]
        c_df = _build_chart_df(
            measures_df=measures_df,
            ratios_df=ratios_df,
            period_labels=c_labels,
            series=series,
            label_prefix="C_",
        )

    mode = decide_chart_render_mode(
        comparison_enabled=comparison_enabled,
        granularity=granularity,
        primary_preset=primary_preset_code,
        comparison_preset=comparison_preset_code,
        primary_period=primary_period,
        comparison_period=comparison_period,
        primary_buckets=primary_buckets,
        comp_buckets=comp_buckets,
    )

    if mode == "aligned_altair":
        aligned_labels = _aligned_bucket_labels(primary_buckets, granularity)
        if not p_df.empty and len(p_df.index) == len(aligned_labels):
            p_df.index = aligned_labels
        if (
            c_df is not None
            and not c_df.empty
            and len(c_df.index) == len(aligned_labels)
        ):
            c_df.index = aligned_labels

    comparison_label = (
        f"Comparison: {comparison_preset_label}" if comparison_preset_label else None
    )

    _render_chart(
        mode=mode,
        kind=kind,
        title=title,
        granularity=granularity,
        primary_label=f"Primary: {primary_preset_label}",
        comparison_label=comparison_label,
        primary_df=p_df,
        comparison_df=c_df,
    )


# -----------------------------------------------------------------------------
# UI render
# -----------------------------------------------------------------------------


def render(app_config: AppConfig, layout: LayoutConfig, page: PageConfig) -> None:
    st.title(_get(page, "title", "Dashboard"))

    # ---- Pull dashboard sections from global layout -------------------------
    # dash = layout.dashboard

    currency_code = app_config.currency
    thousands_separator = getattr(app_config, "thousands_separator", ",")

    allow_secondary_period = bool(_get(page, "allow_secondary_period", True))

    tiles = list(layout.dashboard_tiles or [])
    charts = list(layout.dashboard_charts or [])

    # ---- Period controls (from layout config) --------------------------------
    # NOTE: labels may come from TOML; keep in sync with layout.py parsing.

    page_periods = _get(page, "periods", None)
    periods_cfg = _to_mapping(page_periods)

    # UI labels are stored in page.ui
    ui = _to_mapping(_get(page, "ui", {}))

    primary_labels = _to_mapping(periods_cfg.get("primary_preset_labels", {}))
    comparison_labels = _to_mapping(periods_cfg.get("comparison_preset_labels", {}))
    granularity_labels = _to_mapping(periods_cfg.get("granularity_labels", {}))

    # NEW: user-defined presets from layout_en.toml
    user_presets = _to_mapping(periods_cfg.get("user_presets", {}))
    user_preset_labels: dict[str, str] = {}
    for k, v in user_presets.items():
        if isinstance(v, dict):
            user_preset_labels[str(k).upper()] = str(v.get("label", k))
        else:
            user_preset_labels[str(k).upper()] = str(k)

    def fmt_primary(code: str) -> str:
        c = str(code).upper()
        if c in user_preset_labels:
            return user_preset_labels[c]
        return str(primary_labels.get(c, c))

    def fmt_comparison(code: str) -> str:
        c = str(code).upper()
        if c in user_preset_labels:
            return user_preset_labels[c]
        return str(comparison_labels.get(c, c))

    def fmt_granularity(code: str) -> str:
        code_u = str(code).upper()
        return str(granularity_labels.get(code_u, code_u.lower()))

    # Defaults
    default_primary_preset = (
        periods_cfg.get("default_primary_preset") or "YTD"
    ).upper()
    default_comparison_preset = (
        periods_cfg.get("default_comparison_preset") or "YTD_PREV_FY"
    ).upper()
    default_granularity = (periods_cfg.get("default_granularity") or "MONTH").upper()

    allowed_granularities = [
        str(g).upper() for g in _as_list(periods_cfg.get("allowed_granularities", []))
    ]

    # Built-in presets

    builtin_primary = ["FY", "YTD", "MTD", "LAST_MONTH", "CUSTOM"]
    builtin_comparison = [
        "FY_PREV",
        "YTD_PREV_FY",
        "LAST_MONTH",
        "PREV_PERIOD",
        "SAME_PERIOD_PREV_FY",
        "CUSTOM",
    ]

    # Append user presets (keys from TOML)
    user_preset_keys = [str(k).upper() for k in user_presets.keys()]

    primary_options = builtin_primary + user_preset_keys
    comparison_options = builtin_comparison + user_preset_keys

    # ---- Controls row -------------------------------------------------------
    today = date.today()
    fy = app_config.fiscal_year

    c1, c2, c3 = st.columns([1.2, 1.2, 1.0])

    primary_preset: str
    comparison_preset: Optional[str] = None
    comparison_enabled: bool

    primary_custom_start: Optional[date] = None
    primary_custom_end: Optional[date] = None
    comparison_custom_start: Optional[date] = None
    comparison_custom_end: Optional[date] = None

    # Primary
    with c1:
        with st.container(border=True):
            primary_idx = (
                primary_options.index(default_primary_preset)
                if default_primary_preset in primary_options
                else 0
            )
            primary_preset = st.selectbox(
                ui.get("primary_period_label", "Primary period"),
                options=primary_options,
                index=primary_idx,
                format_func=fmt_primary,
            )

            if primary_preset == "CUSTOM":
                if "p_start" not in st.session_state:
                    st.session_state["p_start"] = fy.start_date
                if "p_end" not in st.session_state:
                    st.session_state["p_end"] = min(fy.end_date, today)

                d1, d2 = st.columns(2)
                with d1:
                    primary_custom_start = st.date_input(
                        ui.get("custom_start_label", "Start date"),
                        key="p_start",
                    )
                with d2:
                    primary_custom_end = st.date_input(
                        ui.get("custom_end_label", "End date"),
                        key="p_end",
                    )

    # Comparison
    with c2:
        with st.container(border=True):
            if allow_secondary_period:
                raw = ui.get("default_enable_comparison", False)
                default_enable = (
                    raw if isinstance(raw, bool) else str(raw).strip().lower() == "true"
                )
                comparison_enabled = st.toggle(
                    ui.get("comparison_toggle_label", "Enable comparison"),
                    value=default_enable,
                )
            else:
                comparison_enabled = False
                st.toggle(
                    ui.get("comparison_toggle_label", "Enable comparison"),
                    value=False,
                    disabled=True,
                )

            if comparison_enabled:
                comp_idx = (
                    comparison_options.index(default_comparison_preset)
                    if default_comparison_preset in comparison_options
                    else 0
                )
                comparison_preset = st.selectbox(
                    ui.get("comparison_period_label", "Comparison period"),
                    options=comparison_options,
                    index=comp_idx,
                    format_func=fmt_comparison,
                )

                if comparison_preset == "CUSTOM":
                    if "c_start" not in st.session_state:
                        st.session_state["c_start"] = fy.start_date
                    if "c_end" not in st.session_state:
                        st.session_state["c_end"] = min(fy.end_date, today)

                    d1, d2 = st.columns(2)
                    with d1:
                        comparison_custom_start = st.date_input(
                            ui.get("custom_start_label", "Start date"),
                            key="c_start",
                        )
                    with d2:
                        comparison_custom_end = st.date_input(
                            ui.get("custom_end_label", "End date"),
                            key="c_end",
                        )

    # Granularity
    with c3:
        with st.container(border=True):
            if not allowed_granularities:
                allowed_granularities = ["DAY", "WEEK", "MONTH", "QUARTER", "FY"]

            granularity = st.selectbox(
                ui.get("granularity_label", "Granularity"),
                options=allowed_granularities,
                index=allowed_granularities.index(default_granularity)
                if default_granularity in allowed_granularities
                else 0,
                format_func=fmt_granularity,
            )

    # ---- Build Period objects ------------------------------------------------
    custom_range_error_msg = ui.get(
        "error_custom_end_before_start", "End date cannot be earlier than start date."
    )

    custom_primary: Optional[CustomRange] = None
    if primary_preset == "CUSTOM":
        if _validate_custom_range(
            primary_custom_start,
            primary_custom_end,
            toast=True,
            error_message=custom_range_error_msg,
        ):
            custom_primary = CustomRange(primary_custom_start, primary_custom_end)

    custom_comp: Optional[CustomRange] = None
    if comparison_enabled and comparison_preset == "CUSTOM":
        if _validate_custom_range(
            comparison_custom_start,
            comparison_custom_end,
            toast=True,
            error_message=custom_range_error_msg,
        ):
            custom_comp = CustomRange(comparison_custom_start, comparison_custom_end)

    # Compute periods (user_presets passed through)
    primary_period = period_from_preset(
        primary_preset,
        fy,
        custom=custom_primary,
        label="PRIMARY",
        user_presets=user_presets,
    )

    comparison_period = None
    if comparison_enabled and comparison_preset:
        rel = comparison_preset.strip().upper()
        if rel in {"PREV_PERIOD", "SAME_PERIOD_PREV_FY"}:
            comparison_period = period_from_relative_preset(
                rel,
                reference=primary_period,
                label="COMPARISON",
            )
        else:
            comparison_period = period_from_preset(
                comparison_preset,
                fy,
                custom=custom_comp,
                label="COMPARISON",
                user_presets=user_presets,
            )

    # Show selected ranges under the selectors (inside containers would need re-layout)

    """
    st.caption(
        f"Primary: {primary_period.start} – {primary_period.end}"
        + (
            f" | Comparison: {comparison_period.start} – {comparison_period.end}"
            if comparison_period is not None
            else ""
        )
    )
    """
    st.markdown(
        f"###### Primary period: {primary_period.start} – {primary_period.end}"
        + (
            f" | Comparison period: {comparison_period.start} – {comparison_period.end}"
            if comparison_period is not None
            else ""
        )
    )

    # ---- Compute ALL periods once (tiles + charts) ---------------------------
    periods_for_compute = [primary_period]
    if comparison_period is not None:
        periods_for_compute.append(comparison_period)

    # chart buckets (page-level granularity)
    primary_buckets = split_period(primary_period, granularity, label_prefix="P_")
    comp_buckets: list[Any] = []
    if comparison_period is not None:
        comp_buckets = split_period(comparison_period, granularity, label_prefix="C_")

    all_periods = periods_for_compute + primary_buckets + comp_buckets

    try:
        _, measures_mp, ratios_mp = compute_all_multi_period(
            app_config=app_config,
            standard_config=app_config.standard_config,
            periods=all_periods,
            ratios_level="full",  # dashboard forces full ratios
        )
        measures_df = measures_mp.data
        ratios_df = ratios_mp.data
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to compute dashboard data: {exc}")
        measures_df = pd.DataFrame()
        ratios_df = pd.DataFrame()

    # ---- Tiles ---------------------------------------------------------------
    st.space(size="small")
    st.subheader(ui.get("section_key_metrics", "Key metrics"))

    cols = st.columns(4) if len(tiles) >= 4 else st.columns(max(1, len(tiles)))
    for i, tile in enumerate(tiles):
        t = _to_mapping(tile)

        label = t.get("label", "Metric")
        source = (t.get("source") or "measure").lower()
        key = t.get("key")
        fmt = t.get("format", "amount")
        tooltip_from = t.get("tooltip_from", "")
        help_text = ""

        show_delta_abs = bool(t.get("show_delta_abs", True))
        show_delta_pct = bool(t.get("show_delta_pct", False))
        delta_good_direction = (t.get("delta_good_direction") or "up").lower()

        primary_val: Optional[float] = None
        comp_val: Optional[float] = None

        if tooltip_from == "measure_notes" and source != "ratio":
            notes = _measure_notes(measures_df, key or "")
            if notes:
                help_text = notes
        elif tooltip_from == "ratio_notes" and source == "ratio":
            notes = _ratio_notes(ratios_df, key or "")
            if notes:
                help_text = notes

        if key:
            if source == "ratio":
                primary_val = _ratio_value(ratios_df, "PRIMARY", key)
                if comparison_period is not None:
                    comp_val = _ratio_value(ratios_df, "COMPARISON", key)
            else:
                primary_val = _measure_value(measures_df, "PRIMARY", key)
                if comparison_period is not None:
                    comp_val = _measure_value(measures_df, "COMPARISON", key)

        delta_abs, delta_pct = _compute_delta(primary_val, comp_val)

        # Choose delta display (Streamlit metric supports only one delta string)
        delta_str = None
        if comparison_period is not None:
            delta_str = _build_delta_string(
                delta_abs=delta_abs,
                delta_pct=delta_pct,
                fmt=fmt,
                show_abs=show_delta_abs,
                show_pct=show_delta_pct,
                currency_code=currency_code,
                thousands_separator=thousands_separator,
            )

        # Streamlit supports delta_color: normal / inverse / off
        # "down" means negative delta is good => inverse
        delta_color = "normal" if delta_good_direction == "up" else "inverse"

        with cols[i % len(cols)]:
            with st.container(border=True):
                st.metric(
                    label=label,
                    value=_fmt_value(
                        primary_val,
                        fmt,
                        currency_code=currency_code,
                        thousands_separator=thousands_separator,
                    ),
                    delta=delta_str,
                    delta_color=delta_color,
                    help=help_text,
                )

    # ---- Charts --------------------------------------------------------------
    st.space(size="small")
    st.subheader(ui.get("section_trends", "Trends"))

    # Helper to normalize strings for matching
    def _norm(s: str) -> str:
        return " ".join((s or "").strip().lower().split())

    # Identify the two charts to show side-by-side
    left_chart = None
    right_chart = None
    remaining: list[Any] = []

    for ch in charts:
        ch_map = _to_mapping(ch)
        title = ch_map.get("title") or ch_map.get("id") or "Chart"
        tnorm = _norm(str(title))

        if tnorm == _norm("Revenue & gross margin evolution"):
            left_chart = ch
        elif tnorm == _norm("Profitability evolution"):
            right_chart = ch
        else:
            remaining.append(ch)

    def _render_chart_container(ch: Any) -> None:
        ch_map = _to_mapping(ch)

        title = ch_map.get("title") or ch_map.get("id") or "Chart"
        kind = (ch_map.get("kind") or "line").lower()
        series = _as_list(ch_map.get("series"))

        with st.container(border=True):
            _render_single_or_side_by_side_chart(
                title=str(title),
                kind=kind,
                measures_df=measures_df,
                ratios_df=ratios_df,
                granularity=granularity,
                primary_preset_code=primary_preset,
                comparison_preset_code=comparison_preset,
                primary_period=primary_period,
                comparison_period=comparison_period,
                primary_buckets=primary_buckets,
                comp_buckets=comp_buckets,
                series=[_to_mapping(s) for s in series],
                comparison_enabled=(comparison_period is not None),
                primary_preset_label=fmt_primary(primary_preset),
                comparison_preset_label=fmt_comparison(comparison_preset or ""),
            )

    # First row: 2 columns (Revenue | Profitability) if present
    if left_chart is not None or right_chart is not None:
        col_l, col_r = st.columns(2)
        with col_l:
            if left_chart is not None:
                _render_chart_container(left_chart)
        with col_r:
            if right_chart is not None:
                _render_chart_container(right_chart)

    # Remaining charts (stacked)
    for ch in remaining:
        _render_chart_container(ch)
