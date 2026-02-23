# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Chart rendering helpers (Dashboard + Ratios pages).

This module renders charts configured in layout TOML into Streamlit, using Altair.

Key concepts
------------
- "Wide" dataframe: index=buckets (x-axis labels), columns=series labels,
values=numbers.
- "Long" dataframe: columns=[bucket, series, value, period_kind, value_fmt, ...]
for Altair.
- period_kind: "Primary" vs "Comparison" when comparison is enabled.

Render modes (ChartRenderMode)
------------------------------
- single: one chart for primary period.
- side_by_side: two charts (Primary | Comparison).
- aligned_altair: Primary + Comparison overlaid on the same bucket axis
(MONTH/QUARTER only).
- indexed_altair: Primary + Comparison overlaid on a synthetic index axis
(DAY/WEEK only: D01.. / W01..).

Policy notes
------------
- Tooltips are formatted with `_fmt_value` (amount/percent/number) and shown
as `value_fmt`.
- For long spans (> 366 days) with infra-annual granularities (DAY/WEEK/MONTH/QUARTER),
  we force side-by-side to avoid misleading overlays / repeated bucket labels.
- Calendar year (CY) and Fiscal year (FY) bucket splitting is handled upstream
by period utilities.
  In comparison mode, CY/FY overlays are intentionally avoided (side-by-side) to
  keep labels truthful.
"""

import calendar
from datetime import date
from typing import Any, Literal, Optional

import altair as alt
import pandas as pd
import streamlit as st

from smb_finsight.periods import Period
from smb_finsight.webui.data_access import _measure_value, _ratio_value
from smb_finsight.webui.formatting import _fmt_value


def _build_chart_df(
    *,
    measures_df: pd.DataFrame,
    ratios_df: pd.DataFrame,
    period_labels: list[str],
    series: list[dict[str, Any]],
    label_prefix: str,
) -> pd.DataFrame:
    """
    Build a "wide" dataframe for chart rendering.

    - Rows represent time buckets (x-axis).
    - Columns represent configured series (human labels).
    - Values are pulled from measures_df or ratios_df for each period label.

    Parameters
    ----------
    period_labels:
        List of period labels used by the computation pipeline. Labels typically
        include a prefix such as "P_" (primary) or "C_" (comparison). This
        function strips `label_prefix` from labels to build a clean bucket index.

    series:
        TOML series definitions. `label` is used as the output column name
        (and becomes the stable series identifier for legends / formatting maps).

    Returns
    -------
    pd.DataFrame
        Wide dataframe: index=bucket labels, columns=series labels.
        Empty dataframe when inputs are empty or period_labels is empty.
    """

    if (measures_df is None or measures_df.empty) and (
        ratios_df is None or ratios_df.empty
    ):
        return pd.DataFrame()
    if not period_labels:
        return pd.DataFrame()

    # Build clean bucket labels for the x-axis (strip "P_" / "C_" prefixes).
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


# Rendering strategies for charts when comparison is enabled.
ChartRenderMode = Literal["single", "side_by_side", "aligned_altair", "indexed_altair"]

# Preset pairs known to be safely "alignable" on the same bucket axis.
# Example: FY vs FY_PREV or SAME_PERIOD_PREV_FY when buckets represent
# the same positions.
_ALIGNED_KNOWN_PAIRS: set[tuple[str, str]] = {
    ("FY", "FY_PREV"),
    ("FY", "SAME_PERIOD_PREV_FY"),
    ("YTD", "YTD_PREV_FY"),
    ("YTD", "SAME_PERIOD_PREV_FY"),
    ("MTD", "SAME_PERIOD_PREV_FY"),
    ("CUSTOM", "SAME_PERIOD_PREV_FY"),
}

# Preset pairs known to be safely "indexable" (same number of buckets)
# even if labels differ.
# Used only for DAY/WEEK, where we generate synthetic axes D01.. / W01..
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


def _period_days(p: Any) -> int:
    """Return inclusive duration in days for objects having .start and .end (date)."""
    if p is None or not hasattr(p, "start") or not hasattr(p, "end"):
        return 0
    return (p.end - p.start).days + 1


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
    Decide how a chart should be rendered when comparison is enabled.

    The decision is based on:
    - whether comparison is enabled and comparison data exists,
    - granularity (DAY/WEEK/MONTH/QUARTER/CY/FY),
    - bucket lengths (primary vs comparison),
    - known preset pairs that can be safely aligned or indexed.

    Modes
    -----
    - "single":
        No comparison (or missing comparison period/preset).
    - "side_by_side":
        Two separate charts (Primary | Comparison). Used as the safest default.
    - "aligned_altair":
        Overlay Primary + Comparison on the same bucket axis.
        Restricted to MONTH/QUARTER and only when buckets are alignable.
    - "indexed_altair":
        Overlay on a synthetic index axis (D01.. or W01..).
        Restricted to DAY/WEEK only.

    Safety rules
    ------------
    - If buckets are missing/empty -> side_by_side.
    - If either period spans > 366 days and granularity is infra-annual
      (DAY/WEEK/MONTH/QUARTER) -> side_by_side to avoid repeated bucket labels.
    - CY/FY in comparison mode -> side_by_side (year-qualified labels are truthful and
      overlays are often misleading when periods cover different years).
    """

    if not comparison_enabled or comparison_period is None or not comparison_preset:
        return "single"

    g = (granularity or "").upper()
    p1 = (primary_preset or "").upper()
    p2 = (comparison_preset or "").upper()

    # If we can't even split properly, safest is side-by-side
    if not primary_buckets or not comp_buckets:
        return "side_by_side"

    # Policy: if either primary or comparison spans > 1 year and granularity is < FY,
    # avoid overlay/indexed charts (which may repeat bucket labels like Jan..Dec).
    # Use side-by-side to preserve truthful bucket labels (often year-qualified).
    if comparison_enabled and comparison_period is not None and comp_buckets:
        if g in {"DAY", "WEEK", "MONTH", "QUARTER"}:
            if (
                _period_days(primary_period) > 366
                or _period_days(comparison_period) > 366
            ):
                return "side_by_side"

    # CY/FY comparison overlays are intentionally disabled: periods commonly
    # cover different years, and "aligned" overlays produce confusing
    # year-qualified axes.

    if g in {"CY", "FY"}:
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
    df_wide: pd.DataFrame,
    *,
    period_kind: str,
    bucket_order: list[str],
    fmt_by_series: dict[str, str] | None = None,
    currency_code: str = "",
    thousands_separator: str = ",",
    series_order: list[str] | None = None,
) -> pd.DataFrame:
    """
    Convert a wide dataframe (index=bucket, columns=series) to a long dataframe
    for Altair.

    Output columns include:
    - bucket: bucket label (categorical with explicit ordering via bucket_order)
    - series: series label (column name from the wide DF)
    - value: numeric value
    - period_kind: "Primary" or "Comparison"
    - value_fmt: formatted value string for tooltips (via `_fmt_value`)

    Notes
    -----
    - bucket_order must contain unique labels. If duplicates exist, pandas will raise.
      Mode selection should prevent overlays that would generate duplicate bucket
      labels.
    - If series_order is provided, the resulting `series` column is made categorical to
      preserve legend order.
    """

    if df_wide is None or df_wide.empty:
        return pd.DataFrame(
            columns=["bucket", "series", "value", "period_kind", "value_fmt"]
        )

    out = df_wide.reset_index().rename(columns={"index": "bucket"})
    long_df = out.melt(id_vars=["bucket"], var_name="series", value_name="value")
    if series_order:
        long_df["series"] = pd.Categorical(
            long_df["series"].astype(str),
            categories=[str(x) for x in series_order],
            ordered=True,
        )
    else:
        long_df["series"] = long_df["series"].astype(str)

    long_df["period_kind"] = period_kind

    # Enforce stable bucket ordering in Altair (and stable legend ordering
    # via categoricals).
    long_df["bucket"] = pd.Categorical(
        long_df["bucket"], categories=bucket_order, ordered=True
    )

    # Format values for tooltips (default to "number" if not specified)
    fmt_map = fmt_by_series or {}

    # Keep the format per series in the long dataframe (used for y-axis formatting).
    # Values: "amount" | "percent" | "number"
    long_df["series_fmt"] = (
        long_df["series"].astype(str).map(fmt_map).fillna("number").astype(str)
    )

    def _fmt_row(r) -> str:
        fmt = fmt_map.get(str(r["series"]), "number")
        return _fmt_value(
            r["value"],
            fmt,
            currency_code=currency_code,
            thousands_separator=thousands_separator,
        )

    long_df["value_fmt"] = long_df.apply(_fmt_row, axis=1)
    return long_df


def _make_index_labels(n: int, granularity: str) -> list[str]:
    """D01.. / W01.. index labels for indexed comparison charts."""
    g = (granularity or "").upper()
    prefix = "W" if g == "WEEK" else "D"
    return [f"{prefix}{i:02d}" for i in range(1, n + 1)]


def _render_altair_lines(df_long: pd.DataFrame, *, title: str, indexed: bool) -> None:
    """
    Render an Altair line chart.

    Supports optional comparison overlay:
    - Primary values are rendered as solid lines.
    - Comparison values are rendered as dashed lines.

    Interaction:
    - Implements "hover anywhere" behaviour using a nearest-point selection
    on the x-axis, so tooltips/markers appear even when hovering empty plot
    area (Streamlit-like UX).

    Legends:
    - Single-series + comparison: legend explains Primary vs Comparison.
    - Multi-series + comparison: series legend + period-style legend (solid/dashed).
    - No comparison: show series legend only if multiple series.
    """

    if df_long is None or df_long.empty:
        st.info("No data.")
        return

    n_series = df_long["series"].nunique() if "series" in df_long.columns else 1

    periods_present = (
        set(df_long["period_kind"].astype(str).unique())
        if "period_kind" in df_long.columns
        else set()
    )
    has_comparison = {"Primary", "Comparison"}.issubset(periods_present)

    series_order = None
    if "series" in df_long.columns and pd.api.types.is_categorical_dtype(
        df_long["series"]
    ):
        series_order = [str(x) for x in df_long["series"].cat.categories]

    is_percent_chart = (
        "series_fmt" in df_long.columns
        and df_long["series_fmt"].astype(str).eq("percent").all()
    )

    enc: dict[str, Any] = {
        "x": alt.X("bucket:N", sort=None, title=None),
        "y": alt.Y(
            "value:Q",
            title=None,
            axis=(alt.Axis(format="%") if is_percent_chart else alt.Axis()),
        ),
        "tooltip": [
            alt.Tooltip("bucket:N", title="Bucket"),
            alt.Tooltip("period_kind:N", title="Period"),
            alt.Tooltip("series:N", title="Series"),
            alt.Tooltip("value_fmt:N", title="Value"),
        ],
    }

    # Legend layout: bottom placement; we often stack vertically to avoid truncation.
    legend_bottom = alt.Legend(
        orient="bottom",
        direction="vertical",
        title=None,
        symbolType="stroke",
    )

    if has_comparison:
        if n_series == 1:
            # ✅ Desired behavior: legend shows only Primary / Comparison (2 items)

            enc["color"] = alt.Color(
                "period_kind:N",
                title=None,
                sort=["Primary", "Comparison"],
                scale=alt.Scale(domain=["Primary", "Comparison"]),
                legend=legend_bottom,  # legend comes from color (2 items)
            )
            enc["strokeDash"] = alt.StrokeDash(
                "period_kind:N",
                sort=["Primary", "Comparison"],
                scale=alt.Scale(
                    domain=["Primary", "Comparison"], range=[[1, 0], [6, 4]]
                ),
                title=None,
                legend=None,  # prevent a 2nd legend
            )

        else:
            # Multiple series: keep series legend, hide Primary/Comparison legend

            if series_order:
                enc["color"] = alt.Color(
                    "series:N",
                    title=None,
                    sort=series_order,
                    scale=alt.Scale(domain=series_order),
                    legend=legend_bottom,
                )
            else:
                enc["color"] = alt.Color("series:N", title=None, legend=legend_bottom)

            # Add a second legend to explain Primary vs Comparison (solid vs dashed).
            # We keep the series legend from `color`, and we expose the period legend
            # from `strokeDash`.
            enc["strokeDash"] = alt.StrokeDash(
                "period_kind:N",
                sort=["Primary", "Comparison"],
                scale=alt.Scale(
                    domain=["Primary", "Comparison"], range=[[1, 0], [6, 4]]
                ),
                title=None,
                legend=alt.Legend(
                    orient="bottom",
                    direction="vertical",
                    title=None,
                    symbolType="stroke",
                ),
            )

    else:
        # No comparison => show series legend only if multiple series
        if n_series > 1:
            if series_order:
                enc["color"] = alt.Color(
                    "series:N",
                    title=None,
                    sort=series_order,
                    scale=alt.Scale(domain=series_order),
                    legend=legend_bottom,
                )
            else:
                enc["color"] = alt.Color("series:N", title=None, legend=legend_bottom)

        # else: no legend at all

    # Base chart with your existing encodings (color/strokeDash/tooltip etc.)
    base = alt.Chart(df_long).encode(**enc)

    lines = base.mark_line()

    # "Hover anywhere" UX: select nearest point along x and show a rule
    # + marker + tooltip.
    nearest = alt.selection_point(
        fields=["bucket"],
        nearest=True,
        on="mousemove",
        empty=False,
    )

    # Invisible layer to capture mouse movement across the plot area
    selectors = (
        alt.Chart(df_long)
        .mark_point(opacity=0)
        .encode(x=alt.X("bucket:N", sort=None))
        .add_params(nearest)
    )

    # Points displayed on the line(s) at the nearest bucket
    points = base.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    )

    # Vertical rule at the nearest bucket for better readability
    rule = (
        alt.Chart(df_long)
        .mark_rule(opacity=0.35)
        .encode(x=alt.X("bucket:N", sort=None))
        .transform_filter(nearest)
    )

    chart = alt.layer(lines, selectors, points, rule).interactive()

    st.altair_chart(chart, width="stretch")


def _render_altair_bars(df_long: pd.DataFrame, *, title: str, indexed: bool) -> None:
    """
    Render an Altair bar chart.

    Supports optional comparison:
    - Single-series + comparison: bars are offset by period_kind (Primary vs Comparison)
      and legend shows Primary/Comparison.
    - Multi-series + comparison: bars are offset using a composite legend key
      ("Primary • <Series>", "Comparison • <Series>") to make comparison explicit.

    Notes:
    - Legend ordering is enforced via categorical series order when available.
    """

    if df_long is None or df_long.empty:
        st.info("No data.")
        return

    n_series = df_long["series"].nunique() if "series" in df_long.columns else 1

    periods_present = (
        set(df_long["period_kind"].astype(str).unique())
        if "period_kind" in df_long.columns
        else set()
    )
    has_comparison = {"Primary", "Comparison"}.issubset(periods_present)

    series_order = None
    if "series" in df_long.columns and pd.api.types.is_categorical_dtype(
        df_long["series"]
    ):
        series_order = [str(x) for x in df_long["series"].cat.categories]

    legend_bottom = alt.Legend(
        orient="bottom",
        direction="vertical",
        title=None,
    )

    is_percent_chart = (
        "series_fmt" in df_long.columns
        and df_long["series_fmt"].astype(str).eq("percent").all()
    )

    enc: dict[str, Any] = {
        "x": alt.X("bucket:N", sort=None, title=None),
        "y": alt.Y(
            "value:Q",
            title=None,
            axis=(alt.Axis(format="%") if is_percent_chart else alt.Axis()),
        ),
        "tooltip": [
            alt.Tooltip("bucket:N", title="Bucket"),
            alt.Tooltip("period_kind:N", title="Period"),
            alt.Tooltip("series:N", title="Series"),
            alt.Tooltip("value_fmt:N", title="Value"),
        ],
    }

    if has_comparison:
        if n_series == 1:
            # ✅ Desired: legend only Primary / Comparison (2 items)

            enc["color"] = alt.Color(
                "period_kind:N",
                title=None,
                sort=["Primary", "Comparison"],
                scale=alt.Scale(domain=["Primary", "Comparison"]),
                legend=legend_bottom,
            )
            # Group bars within each bucket by period_kind
            enc["xOffset"] = alt.XOffset(
                "period_kind:N", sort=["Primary", "Comparison"]
            )
        else:
            # For multi-series + comparison, we create a composite legend key to:
            # - keep exactly one legend,
            # - make Primary vs Comparison explicit for each series,
            # - enforce a stable legend order.

            df_long = df_long.copy()
            df_long["legend_key"] = (
                df_long["period_kind"].astype(str)
                + " • "
                + df_long["series"].astype(str)
            )

            base_series = series_order or (
                df_long["series"].dropna().astype(str).drop_duplicates().tolist()
            )

            legend_order: list[str] = []
            for s in base_series:
                legend_order.append(f"Primary • {s}")
                legend_order.append(f"Comparison • {s}")

            enc["color"] = alt.Color(
                "legend_key:N",
                title=None,
                sort=legend_order,
                scale=alt.Scale(domain=legend_order),
                legend=alt.Legend(
                    orient="bottom",
                    direction="vertical",
                    title=None,
                    columns=2,  # 4 items => 2x2
                ),
            )

            # Group bars side-by-side within each bucket using the same ordering
            enc["xOffset"] = alt.XOffset(
                "legend_key:N",
                sort=legend_order,
            )

    else:
        if n_series > 1:
            if series_order:
                enc["color"] = alt.Color(
                    "series:N",
                    title=None,
                    sort=series_order,
                    scale=alt.Scale(domain=series_order),
                    legend=legend_bottom,
                )
            else:
                enc["color"] = alt.Color("series:N", title=None, legend=legend_bottom)

        # else: no legend

    chart = alt.Chart(df_long).mark_bar().encode(**enc)

    st.altair_chart(chart.interactive(), width="stretch")


def _render_altair_area_line(
    df_long: pd.DataFrame, *, title: str, indexed: bool
) -> None:
    """
    Render an Altair area+line chart.

    Intended for single-series trends (e.g., Revenue evolution).

    Policy
    ------
    - Primary: filled area + solid line.
    - Comparison (if present): dashed line overlay (no filled area).

    If multiple series are present, this function falls back to `_render_altair_lines`
    because multiple overlapping filled areas are hard to read.

    Interaction:
    - Uses the same "hover anywhere" behaviour as line charts (nearest x selection).

    Legends:
    - No comparison: no legend (single series).
    - With comparison: legend explains Primary vs Comparison (solid/dashed).
    """

    if df_long is None or df_long.empty:
        st.info("No data.")
        return

    n_series = df_long["series"].nunique() if "series" in df_long.columns else 1
    if n_series > 1:
        # Multiple filled areas overlap badly; fallback to line overlay.
        _render_altair_lines(df_long, title=title, indexed=indexed)
        return

    # With a single series:
    # - If there is no comparison data, we do NOT want a useless legend.
    # - If there is comparison data, we DO want the legend to distinguish
    #   Primary vs Comparison (not the series name).

    periods_present = (
        set(df_long["period_kind"].astype(str).unique())
        if "period_kind" in df_long.columns
        else set()
    )
    has_comparison = {"Primary", "Comparison"}.issubset(periods_present)

    is_percent_chart = (
        "series_fmt" in df_long.columns
        and df_long["series_fmt"].astype(str).eq("percent").all()
    )

    enc = dict(
        x=alt.X("bucket:N", sort=None, title=None),
        y=alt.Y(
            "value:Q",
            title=None,
            axis=(alt.Axis(format="%") if is_percent_chart else alt.Axis()),
        ),
        tooltip=[
            alt.Tooltip("bucket:N", title="Bucket"),
            alt.Tooltip("period_kind:N", title="Period"),
            alt.Tooltip("series:N", title="Series"),
            alt.Tooltip("value_fmt:N", title="Value"),
        ],
    )

    base = alt.Chart(df_long).encode(**enc)

    primary = base.transform_filter(alt.datum.period_kind == "Primary")
    # comp = base.transform_filter(alt.datum.period_kind == "Comparison")

    # Filled area is intentionally primary-only. Comparison never gets a filled area.
    area = primary.mark_area(opacity=1.00)

    if not has_comparison:
        # Single period: solid line only, no legend
        line = primary.mark_line()

        nearest = alt.selection_point(
            fields=["bucket"],
            nearest=True,
            on="mousemove",
            empty=False,
        )

        selectors = (
            alt.Chart(df_long)
            .mark_point(opacity=0)
            .encode(x=alt.X("bucket:N", sort=None))
            .add_params(nearest)
        )

        points = primary.mark_point().encode(
            opacity=alt.condition(nearest, alt.value(1), alt.value(0))
        )

        rule = (
            alt.Chart(df_long)
            .mark_rule(opacity=0.35)
            .encode(x=alt.X("bucket:N", sort=None))
            .transform_filter(nearest)
        )

        chart = alt.layer(area, line, selectors, points, rule).interactive()
        st.altair_chart(chart, width="stretch")

        return

    # With comparison: one line layer for BOTH periods, dashed encoded by period_kind.
    # This produces a clean legend with 2 line styles (solid/dashed) without
    # hardcoding colors.

    line_both = base.mark_line().encode(
        color=alt.Color(
            "period_kind:N",
            title=None,
            sort=["Primary", "Comparison"],
            scale=alt.Scale(domain=["Primary", "Comparison"]),
            legend=alt.Legend(
                orient="bottom", direction="vertical", title=None, symbolType="stroke"
            ),
        ),
        strokeDash=alt.StrokeDash(
            "period_kind:N",
            sort=["Primary", "Comparison"],
            scale=alt.Scale(domain=["Primary", "Comparison"], range=[[1, 0], [6, 4]]),
            title=None,
            legend=None,
        ),
    )

    # Ensure comparison has no filled area
    # (already true because area is primary-filtered)

    nearest = alt.selection_point(
        fields=["bucket"],
        nearest=True,
        on="mousemove",
        empty=False,
    )

    selectors = (
        alt.Chart(df_long)
        .mark_point(opacity=0)
        .encode(x=alt.X("bucket:N", sort=None))
        .add_params(nearest)
    )

    # Points on BOTH periods (Primary + Comparison), but no filled area for Comparison.
    points = base.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    )

    rule = (
        alt.Chart(df_long)
        .mark_rule(opacity=0.35)
        .encode(x=alt.X("bucket:N", sort=None))
        .transform_filter(nearest)
    )

    chart = alt.layer(area, line_both, selectors, points, rule).interactive()
    st.altair_chart(chart, width="stretch")


def _render_altair_overlay(
    df_long: pd.DataFrame, *, title: str, indexed: bool, kind: str
) -> None:
    """
    Render an Altair overlay chart from a long dataframe containing BOTH periods.

    This is used when comparison is enabled and we want a single chart overlay:
    - aligned_altair: shared bucket labels (MONTH/QUARTER)
    - indexed_altair: synthetic index axis (DAY/WEEK)

    Dispatches to either line/bar/area_line overlay rendering according to `kind`.
    """

    k = (kind or "line").lower().strip()
    if k == "bar":
        _render_altair_bars(df_long, title=title, indexed=indexed)
        return
    if k == "area_line":
        _render_altair_area_line(df_long, title=title, indexed=indexed)
        return
    # default
    _render_altair_lines(df_long, title=title, indexed=indexed)


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
    fmt_by_series: dict[str, str],
    currency_code: str,
    thousands_separator: str,
    series_order: list[str] | None = None,
) -> None:
    """
    Render a chart according to the decided mode.

    All render paths use Altair so we can:
    - control legend ordering and layout,
    - provide consistent, formatted tooltips (value_fmt),
    - implement "hover anywhere" behaviour (nearest x selection).

    Modes
    -----
    - single: one Altair chart (primary only)
    - side_by_side: two Altair charts in 2 columns (Primary | Comparison)
    - aligned_altair: one Altair overlay chart sharing the same bucket axis
    - indexed_altair: one Altair overlay chart using D01/W01 synthetic axis

    Kind
    ----
    kind in {"line", "bar", "area_line"}:
    - line: lines (optionally dashed for comparison)
    - bar: bars (optionally grouped/offset for comparison)
    - area_line: primary area + line, with optional comparison line overlay

    Formatting
    ----------
    - fmt_by_series influences tooltip formatting and percent-axis display.
    - When a chart is a pure percent chart, the y-axis is formatted as percentages.
    """

    k = (kind or "line").lower().strip()
    if k not in {"line", "bar", "area_line"}:
        st.info(f"Unsupported chart kind '{k}'. Falling back to 'line'.")
        k = "line"

    # If only one bucket exists, a bar is usually clearer than a line
    # (single-point line is odd).
    def _should_bar(df: pd.DataFrame) -> bool:
        return df is not None and not df.empty and len(df.index) <= 1

    def _render_area_line_single(df: pd.DataFrame) -> None:
        """
        Render an area_line chart using Altair for a single wide dataframe
        (no comparison overlay).
        """
        if df is None or df.empty:
            st.info("No data.")
            return

        bucket_order = list(df.index)
        df_long = _wide_to_long(
            df,
            period_kind="Primary",
            bucket_order=bucket_order,
            fmt_by_series=fmt_by_series,
            currency_code=currency_code,
            thousands_separator=thousands_separator,
            series_order=series_order,
        )
        _render_altair_area_line(df_long, title=title, indexed=False)

    def _render_altair_single(df: pd.DataFrame, *, period_kind: str) -> None:
        """
        Render a non-overlay Altair chart (line or bar) for one wide DF.

        Used to keep legend order stable in side_by_side mode when n_series > 1.
        """
        if df is None or df.empty:
            st.info("No data.")
            return

        bucket_order = list(df.index)
        df_long = _wide_to_long(
            df,
            period_kind=period_kind,
            bucket_order=bucket_order,
            fmt_by_series=fmt_by_series,
            currency_code=currency_code,
            thousands_separator=thousands_separator,
            series_order=series_order,
        )

        if k == "bar" or _should_bar(df):
            _render_altair_bars(df_long, title=title, indexed=False)
        else:
            _render_altair_lines(df_long, title=title, indexed=False)

    if mode == "single":
        if primary_df is None or primary_df.empty:
            st.info("No data.")
            return

        # area_line must always render as Altair area, even without comparison.
        if k == "area_line" and not _should_bar(primary_df):
            _render_area_line_single(primary_df)
            return

        # ✅ For multi-series charts, use Altair even in single mode,
        # so legend order matches the config (series_order).
        n_series = len(primary_df.columns) if primary_df is not None else 0
        if n_series > 1:
            bucket_order = list(primary_df.index)
            df_long = _wide_to_long(
                primary_df,
                period_kind="Primary",
                bucket_order=bucket_order,
                fmt_by_series=fmt_by_series,
                currency_code=currency_code,
                thousands_separator=thousands_separator,
                series_order=series_order,
            )
            # Render as Altair (no comparison overlay)
            if k == "bar" or _should_bar(primary_df):
                _render_altair_bars(df_long, title=title, indexed=False)
            else:
                _render_altair_lines(df_long, title=title, indexed=False)
            return

        # Single-series: use Altair too (so tooltips are formatted consistently)
        _render_altair_single(primary_df, period_kind="Primary")
        return

    if mode == "side_by_side":
        left, right = st.columns(2)

        with left:
            st.caption(f"{primary_label}")
            if primary_df is None or primary_df.empty:
                st.info("No data.")
            else:
                if k == "area_line" and not _should_bar(primary_df):
                    _render_area_line_single(primary_df)
                else:
                    _render_altair_single(primary_df, period_kind="Primary")

        with right:
            st.caption(f"{comparison_label}")
            if comparison_df is None or comparison_df.empty:
                st.info("No data.")
            else:
                if k == "area_line" and not _should_bar(primary_df):
                    _render_area_line_single(comparison_df)
                else:
                    _render_altair_single(comparison_df, period_kind="Comparison")

        return

    # Altair modes
    if comparison_df is None or comparison_df.empty:
        # if no comp data, fallback to single
        if primary_df is None or primary_df.empty:
            st.info("No data.")
            return
        if k == "area_line":
            _render_area_line_single(primary_df)
            return
        _render_altair_single(primary_df, period_kind="Primary")
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
                _wide_to_long(
                    p,
                    period_kind="Primary",
                    bucket_order=bucket_order,
                    fmt_by_series=fmt_by_series,
                    currency_code=currency_code,
                    thousands_separator=thousands_separator,
                    series_order=series_order,
                ),
                _wide_to_long(
                    c,
                    period_kind="Comparison",
                    bucket_order=bucket_order,
                    fmt_by_series=fmt_by_series,
                    currency_code=currency_code,
                    thousands_separator=thousands_separator,
                    series_order=series_order,
                ),
            ],
            ignore_index=True,
        )
        _render_altair_overlay(df_long, title=title, indexed=True, kind=k)

        return

    if mode == "aligned_altair":
        # Keep bucket labels as-is (e.g. Jan..Dec or Q1..Q4)
        bucket_order = list(primary_df.index)
        df_long = pd.concat(
            [
                _wide_to_long(
                    primary_df,
                    period_kind="Primary",
                    bucket_order=bucket_order,
                    fmt_by_series=fmt_by_series,
                    currency_code=currency_code,
                    thousands_separator=thousands_separator,
                    series_order=series_order,
                ),
                _wide_to_long(
                    comparison_df,
                    period_kind="Comparison",
                    bucket_order=bucket_order,
                    fmt_by_series=fmt_by_series,
                    currency_code=currency_code,
                    thousands_separator=thousands_separator,
                    series_order=series_order,
                ),
            ],
            ignore_index=True,
        )
        _render_altair_overlay(df_long, title=title, indexed=False, kind=k)

        return


def _aligned_bucket_labels(buckets: list[Any], granularity: str) -> list[str]:
    # Defensive helper: mode selection should prevent CY/FY aligned overlays
    # in comparison, but we keep label handling here as a safe fallback.

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

    if g in {"CY", "FY"}:
        return [b.label for b in buckets]

    # fallback: keep current labels
    return [str(getattr(b, "label", "")) for b in buckets]


def _render_configured_chart_impl(
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
    primary_buckets: list[Period],
    comp_buckets: list[Period],
    series: list[dict[str, Any]],
    comparison_enabled: bool,
    primary_preset_label: str,
    comparison_preset_label: str,
    currency_code: str,
    thousands_separator: str,
) -> None:
    """
    Render one chart container (title + chosen render mode).

    This is the entry-point used by dashboard sections. It builds wide dataframes for
    primary/comparison buckets and delegates the rendering decision to
    `decide_chart_render_mode()`.
    """

    st.markdown(f"###### {title}")

    # Build a per-series format map (same policy as tiles / Ratios area chart)
    fmt_by_series: dict[str, str] = {}
    series_order: list[str] = []

    for s in series:
        src = str(s.get("source") or "measure").lower()
        key = str(s.get("key") or "")
        label = str(s.get("label") or key).strip()
        if not label:
            label = key  # safety
        series_order.append(label)

        # Prefer explicit TOML format if provided (layout_en.toml series format="...")
        raw_fmt = str(s.get("format") or "").strip().lower()
        if raw_fmt in {"amount", "percent", "number"}:
            fmt_by_series[label] = raw_fmt
        else:
            # Backward-compatible default policy
            if src == "measure":
                fmt_by_series[label] = "amount"
            else:
                fmt_by_series[label] = "percent" if key.endswith("_pct") else "number"

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
        fmt_by_series=fmt_by_series,
        currency_code=currency_code,
        thousands_separator=thousands_separator,
        series_order=series_order,
    )


def render_area_line_chart(
    *,
    title: str,
    measures_df: pd.DataFrame,
    ratios_df: pd.DataFrame,
    period_labels: list[str],
    label_prefix: str,
    series: list[dict[str, Any]],
    currency_code: str,
    thousands_separator: str,
    fill_missing_zero: bool,
) -> None:
    """
    Render a single-period area+line chart (no comparison overlay).

    This helper is primarily used by the Ratios page, which renders charts from
    the global granularity and uses formatted tooltips via `_fmt_value`.

    Formatting policy:
    - Per-series formatting can be explicitly set in TOML
    (series format="amount|percent|number").
    - If not provided, defaults are inferred:
        - measures -> amount
        - ratios ending with _pct -> percent
        - otherwise -> number

    Note:
    - This function builds a wide DF, converts it to long via `_wide_to_long`,
      then renders via Altair (area + line).
    """

    if not period_labels:
        st.info("No data.")
        return

    df_wide = _build_chart_df(
        measures_df=measures_df,
        ratios_df=ratios_df,
        period_labels=period_labels,
        series=series,
        label_prefix=label_prefix,
    )
    if df_wide is None or df_wide.empty:
        st.info("No data.")
        return

    if fill_missing_zero:
        df_wide = df_wide.fillna(0.0)

    # Build a per-series format map (reuse existing tile policy)
    fmt_by_series: dict[str, str] = {}
    for s in series:
        src = str(s.get("source") or "measure").lower()
        key = str(s.get("key") or "")
        label = str(s.get("label") or key)

        # Determine tooltip/axis formatting per series.
        # Prefer explicit TOML format if provided (layout_en.toml series format="...")
        raw_fmt = str(s.get("format") or "").strip().lower()
        if raw_fmt in {"amount", "percent", "number"}:
            fmt_by_series[label] = raw_fmt
        else:
            # Backward-compatible default policy
            if src == "measure":
                fmt_by_series[label] = "amount"
            else:
                fmt_by_series[label] = "percent" if key.endswith("_pct") else "number"

    # Wide -> long for Altair
    bucket_order = list(df_wide.index)
    df_long = _wide_to_long(
        df_wide,
        period_kind="Primary",
        bucket_order=bucket_order,
        fmt_by_series=fmt_by_series,
        currency_code=currency_code,
        thousands_separator=thousands_separator,
    )

    # If all series are explicitly formatted as percent,
    # display y-axis as % (0..1 -> 0%..100%).
    is_percent_chart = (
        "series_fmt" in df_long.columns
        and df_long["series_fmt"].astype(str).eq("percent").all()
    )
    y_axis = alt.Axis(format="%") if is_percent_chart else alt.Axis()

    base = alt.Chart(df_long).encode(
        x=alt.X("bucket:N", sort=None, title=None),
        y=alt.Y("value:Q", title=None, axis=y_axis),
        color=alt.Color("series:N", title=None),
        tooltip=[
            alt.Tooltip("bucket:N", title="Bucket"),
            alt.Tooltip("series:N", title="Series"),
            alt.Tooltip("value_fmt:N", title="Value"),
        ],
    )

    area = base.mark_area(opacity=0.25)
    line = base.mark_line()

    st.altair_chart(area + line, width="stretch")


def render_configured_chart(
    *,
    title: str,
    kind: str,
    series: list[dict[str, Any]],
    measures_df: pd.DataFrame,
    ratios_df: pd.DataFrame,
    granularity: str,
    primary_period: Period,
    comparison_period: Period | None,
    primary_preset_code: str,
    comparison_preset_code: str | None,
    primary_preset_label: str,
    comparison_preset_label: str,
    primary_buckets: list[Period],
    comparison_buckets: list[Period],
    comparison_enabled: bool,
    currency_code: str,
    thousands_separator: str,
) -> None:
    """
    Render a configured chart (Dashboard/Ratios) using the shared rendering modes:
    single, side_by_side, aligned_altair, indexed_altair.

    Notes:
    - `kind` maps to the TOML chart type: "line", "bar", "area_line".
    - The render mode is chosen automatically based on period presets and granularity.
    """
    _render_configured_chart_impl(
        title=title,
        kind=kind,
        measures_df=measures_df,
        ratios_df=ratios_df,
        granularity=granularity,
        primary_preset_code=primary_preset_code,
        comparison_preset_code=comparison_preset_code,
        primary_period=primary_period,
        comparison_period=comparison_period,
        primary_buckets=primary_buckets,
        comp_buckets=comparison_buckets,
        series=series,
        comparison_enabled=comparison_enabled,
        primary_preset_label=primary_preset_label,
        comparison_preset_label=comparison_preset_label,
        currency_code=currency_code,
        thousands_separator=thousands_separator,
    )
