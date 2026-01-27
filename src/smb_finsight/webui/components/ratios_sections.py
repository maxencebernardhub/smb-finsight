# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Ratios & KPIs sections renderer (WebUI).

This renderer is configuration-driven via layout TOML:

    [ratios_page]
    [[ratios_page.sections]]
      - [[ratios_page.sections.tiles]]: list of tiles (measures and ratios)
      - [[ratios_page.sections.charts]] : list of charts

Key principles
--------------
- Keep the Ratios page file thin: rendering logic lives here.
- Reuse the existing tile renderer:
    smb_finsight.webui.components.metric_tiles.render_metric_tiles
  to guarantee consistent formatting and delta semantics across pages.
- Preserve ordering exactly as defined in the TOML.

Tooltip policy (Ratios V2)
--------------------------
- Each Ratios tile may define `tooltip_from` as a *literal text override*.
  When present, it must replace the pack notes.
- Otherwise, tooltips can source from pack notes via:
    - "measure_notes" for measures
    - "ratio_notes" for ratios

Implementation note:
- `render_metric_tiles()` only knows note-sourcing. Therefore we pass
  an explicit `tooltip_text` field to tiles and patch metric_tiles to
  prioritize it when present (backward-compatible).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd
import streamlit as st

from smb_finsight.periods import Period
from smb_finsight.webui.components.charts import render_configured_chart
from smb_finsight.webui.components.metric_tiles import render_metric_tiles
from smb_finsight.webui.utils import _to_mapping

# -----------------------------------------------------------------------------
# Public API
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class RatiosSectionsContext:
    """
    Rendering context for the Ratios sections.

    Attributes:
        measures_df: Multi-period measures dataframe (from pipeline).
        ratios_df: Multi-period ratios dataframe (from pipeline).
        comparison_enabled: Whether a comparison period is active.
        currency_code: Currency code used by formatting helpers.
        thousands_separator: Thousands separator ("," or " ").
        granularity: Granularity string.
        primary_period: Primary period object.
        comparison_period: Comparison period object (or None).
        primary_preset_code: Primary preset code string.
        comparison_preset_code: Comparison preset code string (or None).
        primary_preset_label: Primary preset label string.
        comparison_preset_label: Comparison preset label string (or None).
        primary_buckets: Bucket periods for the primary selection.
        comp_buckets: Bucket periods for the comparison selection.

    """

    measures_df: pd.DataFrame
    ratios_df: pd.DataFrame
    comparison_enabled: bool
    currency_code: str
    thousands_separator: str
    granularity: str
    primary_period: Period
    comparison_period: Period | None
    primary_preset_code: str
    comparison_preset_code: str | None
    primary_preset_label: str
    comparison_preset_label: str
    primary_buckets: list[Period]
    comp_buckets: list[Period]


def render_ratios_sections(
    *, sections: Sequence[Any], ctx: RatiosSectionsContext
) -> None:
    """
    Render all Ratios sections in order.

    Args:
        sections: Parsed section configs from layout.ratios_page.sections.
                  Items are dataclasses or dict-like objects.
        ctx: Rendering context.
    """
    sections_list = list(sections or [])
    if not sections_list:
        st.info("No sections configured for Ratios & KPIs.")
        return

    for section in sections_list:
        _render_one_section(section=section, ctx=ctx)


# -----------------------------------------------------------------------------
# Section rendering
# -----------------------------------------------------------------------------


def _render_one_section(*, section: Any, ctx: RatiosSectionsContext) -> None:
    s = _to_mapping(section)

    # st.divider()
    st.subheader(s.get("title", "Section"))

    tiles_raw = list(s.get("tiles") or [])
    if tiles_raw:
        tiles = [_ratios_tile_to_metric_tile(t, ctx=ctx) for t in tiles_raw]
        render_metric_tiles(
            tiles=tiles,
            measures_df=ctx.measures_df,
            ratios_df=ctx.ratios_df,
            comparison_enabled=ctx.comparison_enabled,
            currency_code=ctx.currency_code,
            thousands_separator=ctx.thousands_separator,
        )

    # charts
    charts = list(s.get("charts") or [])
    if charts:
        _render_section_charts(section=s, charts=charts, ctx=ctx)

    st.space(size="small")


def _render_section_charts(
    *, section: dict[str, Any], charts: list[Any], ctx: RatiosSectionsContext
) -> None:
    """
    Render charts configured under one ratios section.

    Layout policy:
    - charts are displayed after the tiles of the section
    - 5 columns grid (5 charts per row)
    - charts follow global page granularity; no per-chart controls
    """
    sec_id = str(section.get("id") or "section")

    cols = st.columns(5)
    for i, ch in enumerate(charts):
        ch_map = _to_mapping(ch)
        with cols[i % 5]:
            with st.container(border=True):
                _render_one_chart(section_id=sec_id, chart=ch_map, ctx=ctx)


def _render_one_chart(
    *, section_id: str, chart: dict[str, Any], ctx: RatiosSectionsContext
) -> None:
    """
    Render a single chart inside a Ratios section.

    Charts always follow the global page granularity.
    Buckets come from ctx.primary_buckets, computed once
    by the pipeline using the global granularity.
    """

    chart_id = str(chart.get("id") or "chart")
    title = str(chart.get("title") or chart_id)
    chart_type = str(chart.get("type") or "line").lower()

    # st.markdown(f"###### {title}")

    # Buckets (global granularity only)
    period_labels = [b.label for b in (ctx.primary_buckets or [])]

    if not period_labels:
        st.info("No data.")
        return

    # Render chart
    series = list(chart.get("series") or [])
    render_configured_chart(
        title=title,
        kind=chart_type,  # "area_line" / "line" / "bar"
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
        comparison_buckets=ctx.comp_buckets,
        comparison_enabled=ctx.comparison_enabled,
        currency_code=ctx.currency_code,
        thousands_separator=ctx.thousands_separator,
    )


# -----------------------------------------------------------------------------
# Tile conversion (RatiosTileSpec -> metric_tiles tile mapping)
# -----------------------------------------------------------------------------


def _ratios_tile_to_metric_tile(
    tile: Any, *, ctx: RatiosSectionsContext
) -> dict[str, Any]:
    """
    Convert a Ratios tile spec (dataclass/dict) to a mapping compatible with
    `render_metric_tiles()`.

    Expected Ratios tile fields (layout):
        - source (str: "measure"|"ratio") [required]
        - key (str) [required]
        - delta_good_direction (str: "up"|"down") [required]
        - label (str) [optional override]
        - show_delta_abs (bool) [optional override]
        - show_delta_pct (bool) [optional override]
        - tooltip_from (str) [optional text override or empty]
    """
    t = _to_mapping(tile)

    source = (t.get("source") or "measure").strip().lower()
    if source not in {"measure", "ratio"}:
        source = "measure"

    key = (t.get("key") or "").strip()

    # required
    delta_good_direction = (t.get("delta_good_direction") or "up").strip().lower()
    if delta_good_direction not in {"up", "down"}:
        delta_good_direction = "up"

    # optional overrides
    label_override = t.get("label")
    show_delta_abs = t.get("show_delta_abs")
    show_delta_pct = t.get("show_delta_pct")

    # Tooltip override string (Ratios V2): treat as final text if provided
    tooltip_override_text = (t.get("tooltip_from") or "").strip()

    # Label: if not provided, fallback to pack label from df
    label = (
        label_override or _lookup_label_from_df(ctx, tile_kind=source, key=key) or key
    )
    label = label.strip() if isinstance(label, str) else key

    # Format: infer from pack unit column (amount/percent/days/ratio/number)
    fmt = _infer_fmt_from_unit(ctx, tile_kind=source, key=key)

    # Notes sourcing:
    # - if override tooltip text is provided -> pass tooltip_text to metric_tiles
    # - else -> tell metric_tiles to source from pack notes
    if tooltip_override_text:
        tooltip_text = tooltip_override_text
        tooltip_from = ""  # ignored when tooltip_text is present (after patch)
    else:
        tooltip_text = ""
        tooltip_from = "measure_notes" if source == "measure" else "ratio_notes"

    # Delta defaults:
    # - measures: abs + pct by default
    # - ratios:   abs only by default (pct delta on a ratio is often noisy)
    if show_delta_abs is None:
        show_delta_abs = True
    if show_delta_pct is None:
        show_delta_pct = True if source == "measure" else False

    return {
        # metric_tiles expects these keys
        "label": label,
        "source": source,
        "key": key,
        "format": fmt,
        "tooltip_from": tooltip_from,
        "tooltip_text": tooltip_text,  # requires tiny patch in metric_tiles.py
        "show_delta_abs": bool(show_delta_abs),
        "show_delta_pct": bool(show_delta_pct),
        "delta_good_direction": delta_good_direction,
    }


def _lookup_label_from_df(
    ctx: RatiosSectionsContext, *, tile_kind: str, key: str
) -> str:
    """
    Fetch display label from computed multi-period outputs.

    measures_df schema: measure_key, label, ...
    ratios_df schema:   key, label, ...
    """
    if not key:
        return ""

    try:
        if tile_kind == "measure":
            df = ctx.measures_df
            rows = df[df["measure_key"] == key]
        else:
            df = ctx.ratios_df
            rows = df[df["key"] == key]
        if rows.empty:
            return ""
        v = rows.iloc[0].get("label", "")
        return v.strip() if isinstance(v, str) else ""
    except Exception:
        return ""


def _infer_fmt_from_unit(
    ctx: RatiosSectionsContext, *, tile_kind: str, key: str
) -> str:
    """
    Infer `formatting._fmt_value` fmt from the `unit` column.

    Supported by formatting.py:
        - amount
        - percent
        - ratio
        - number (fallback)
        - float/int are also accepted by _fmt_value

    Multi-period schemas (multi_periods.py):
        measures_df has `unit`
        ratios_df has `unit`
    """
    unit = ""
    try:
        if tile_kind == "measure":
            rows = ctx.measures_df[ctx.measures_df["measure_key"] == key]
        else:
            rows = ctx.ratios_df[ctx.ratios_df["key"] == key]
        if not rows.empty:
            u = rows.iloc[0].get("unit", "")
            unit = u.strip().lower() if isinstance(u, str) else ""
    except Exception:
        unit = ""

    # Normalize unit -> fmt
    if unit in {"amount", "currency", "money"}:
        return "amount"
    if unit in {"percent", "%", "pct"}:
        return "percent"
    if unit in {"ratio", "multiple"}:
        return "ratio"
    if unit in {"days", "day"}:
        # formatting.py doesn't have a dedicated "days" branch yet;
        # number is acceptable and keeps formatting stable.
        return "number"

    # fallback
    return "number"
