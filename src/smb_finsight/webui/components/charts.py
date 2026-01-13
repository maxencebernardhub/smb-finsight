# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Chart rendering utilities (WebUI).

This module renders time-series charts for the Dashboard (and future Ratios
& KPIs page).
It supports multiple comparison render strategies depending on period presets
and granularity:

- single: render primary series only (Streamlit line/bar)
- side_by_side: render primary and comparison in two Streamlit charts
- aligned_altair: overlay primary + comparison on the same bucket axis (MONTH/QUARTER)
- indexed_altair: overlay primary + comparison on a synthetic index axis
(DAY/WEEK: D01.. / W01..)

Data expectations:
- measures_df / ratios_df are multi-period outputs indexed by a `period_label`
(e.g. "P_2025-01", "C_2024-01").
- `primary_buckets` / `comp_buckets` are lists of Period-like objects with
`.label` and `.start`/`.end`.

Notes:
- Bucket labels for aligned_altair are currently English ("Jan".."Dec", "Q1".."Q4").
  Localization can be added later through layout TOML if needed.
"""

import calendar
from datetime import date
from typing import Any, Literal, Optional

import altair as alt
import pandas as pd
import streamlit as st

from smb_finsight.webui.data_access import _measure_value, _ratio_value


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
    - "single"
    - "side_by_side"
    - "aligned_altair"
    - "indexed_altair"

    Note: `comp_buckets` is expected to be an empty list when comparison is disabled.

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
    - bucket (str, categorical ordered via `bucket_order` in `_wide_to_long`)
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
            sort=None,  # keep the categorical order as provided by `_wide_to_long`
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

    """
    Render one chart container (title + chosen render mode).

    This is the entry-point used by dashboard sections. It builds wide dataframes for
    primary/comparison buckets and delegates the rendering decision to
    `decide_chart_render_mode()`.
    """

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

    # `comparison_preset_label` may be an empty string depending on caller;
    # treat empty as absent.
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
