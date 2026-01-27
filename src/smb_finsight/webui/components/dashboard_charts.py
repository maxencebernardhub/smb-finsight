# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Dashboard charts section renderer (WebUI).

This module implements the layout policy for the Dashboard 'Trends' section:
- pick two "featured" charts (left/right) and render them side-by-side,
- render all remaining charts full-width below.

It is intentionally page-specific (Dashboard only). Generic chart computation and
rendering lives in:
- smb_finsight.webui.components.charts

Design note:
The featured-chart selection currently matches charts by their *title*
(case/whitespace-insensitive).
This is a pragmatic v0.5.0 approach; in the future, prefer stable chart IDs
from layout TOML.
"""

from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd
import streamlit as st

from smb_finsight.webui.components.charts import render_configured_chart
from smb_finsight.webui.utils import _as_list, _to_mapping


@dataclass(frozen=True)
class DashboardChartsContext:
    """
    Immutable context required to render Dashboard charts.

    This is passed explicitly instead of relying on closures to keep dashboard.py thin.
    Most fields come from:
    - period selection (primary/comparison presets and labels),
    - the dashboard compute pipeline output (measures/ratios DataFrames, buckets).
    """

    # Multi-period outputs (rows include PRIMARY/COMPARISON + bucket periods)
    measures_df: pd.DataFrame
    ratios_df: pd.DataFrame

    # Bucket granularity for time-series charts (DAY/WEEK/MONTH/QUARTER/FY)
    granularity: str

    primary_preset_code: str
    comparison_preset_code: Optional[str]

    primary_period: Any
    comparison_period: Optional[Any]

    # Buckets used for chart x-axis (label_prefix applied in pipeline)
    primary_buckets: list[Any]
    comp_buckets: Optional[list[Any]]

    comparison_enabled: bool

    primary_preset_label: str
    comparison_preset_label: Optional[str]

    # Formatting for tooltips (shared with tiles)
    currency_code: str
    thousands_separator: str


def _norm(s: str) -> str:
    """Normalize a title for robust comparisons
    (trim, collapse whitespace, lowercase)."""
    return " ".join((s or "").strip().lower().split())


def _render_chart_container(*, ch: Any, ctx: DashboardChartsContext) -> None:
    """
    Render one chart container based on a single chart config entry.

    `ch` is a chart mapping from layout TOML (dashboard.charts).
    """

    ch_map = _to_mapping(ch)

    title = ch_map.get("title") or ch_map.get("id") or "Chart"
    kind = (ch_map.get("kind") or ch_map.get("type") or "line").lower().strip()
    series = _as_list(ch_map.get("series"))

    # Delegate actual series rendering + mode selection to the generic charts component.
    with st.container(border=True, height="stretch"):
        render_configured_chart(
            title=str(title),
            kind=kind,
            series=[_to_mapping(s) for s in series],
            measures_df=ctx.measures_df,
            ratios_df=ctx.ratios_df,
            granularity=ctx.granularity,
            primary_period=ctx.primary_period,
            comparison_period=ctx.comparison_period,
            primary_preset_code=ctx.primary_preset_code,
            comparison_preset_code=ctx.comparison_preset_code,
            primary_preset_label=ctx.primary_preset_label,
            comparison_preset_label=ctx.comparison_preset_label,
            primary_buckets=ctx.primary_buckets,
            comparison_buckets=ctx.comp_buckets or [],
            comparison_enabled=ctx.comparison_enabled,
            currency_code=ctx.currency_code,
            thousands_separator=ctx.thousands_separator,
        )


def render_dashboard_trends_charts(
    *, charts: list[Any], ctx: DashboardChartsContext
) -> None:
    """
    Render the Dashboard 'Trends' charts section.

    Layout policy (v0.5.0):
    - select two featured charts by normalized title
    ("Revenue evolution" and "Profitability evolution"),
      render them side-by-side if present;
    - render all remaining charts full-width below.

    NOTE: Title-based selection is fragile under localization or renaming.
    A future improvement is to select by stable chart IDs from the TOML config.
    """

    left_chart = None
    right_chart = None
    remaining: list[Any] = []

    # Featured charts are currently selected by title (normalized).
    # Keep titles stable in layout_en.toml.
    for ch in charts:
        ch_map = _to_mapping(ch)
        title = str(ch_map.get("title") or ch_map.get("id") or "")
        tnorm = _norm(title)

        if tnorm == _norm("Revenue & gross margin evolution"):
            left_chart = ch
        elif tnorm == _norm("Profitability evolution"):
            right_chart = ch
        else:
            remaining.append(ch)

    # First row: 2 columns (Revenue | Profitability) if present
    if left_chart is not None or right_chart is not None:
        col_l, col_r = st.columns(2)
        with col_l:
            if left_chart is not None:
                _render_chart_container(ch=left_chart, ctx=ctx)
        with col_r:
            if right_chart is not None:
                _render_chart_container(ch=right_chart, ctx=ctx)

    # Remaining charts: full width, one per container
    for ch in remaining:
        _render_chart_container(ch=ch, ctx=ctx)
