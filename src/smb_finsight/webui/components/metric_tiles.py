# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Dashboard metric tiles renderer (WebUI).

This module renders the KPI tiles displayed at the top of the Dashboard page.
Tiles are configuration-driven (layout TOML) and can source values from:
- measures_df (canonical measures)
- ratios_df (derived ratios)

Streamlit constraint:
- `st.metric()` accepts a single delta string, so this module builds a combined delta
  string according to tile settings (abs and/or pct).

Finance conventions implemented:
- For percent tiles:
  - abs-only deltas are displayed as percentage points (pp), e.g. 4% -> 3% => "-1.00 pp"
  - this avoids ambiguous "percent of percent" deltas.
- delta_good_direction controls Streamlit delta_color:
  - "up"     -> "normal"  (positive is good)
  - "down"   -> "inverse" (negative is good)
"""

from typing import Any, Optional

import pandas as pd
import streamlit as st

from smb_finsight.webui.data_access import (
    _measure_notes,
    _measure_value,
    _ratio_notes,
    _ratio_value,
)
from smb_finsight.webui.formatting import (
    _build_delta_string,
    _compute_delta,
    _fmt_value,
    _format_pp,
)
from smb_finsight.webui.utils import _to_mapping


def render_metric_tiles(
    *,
    tiles: list[Any],
    measures_df: pd.DataFrame,
    ratios_df: pd.DataFrame,
    comparison_enabled: bool,
    currency_code: str,
    thousands_separator: str,
) -> None:
    """
    Render dashboard KPI tiles (Streamlit `st.metric`).

    Args:
        tiles: List of tile config mappings from layout TOML (`[[dashboard.tiles]]`).
        They are normalized via `_to_mapping`.
        measures_df: Multi-period measures output
        (must include PRIMARY/COMPARISON rows).
        ratios_df: Multi-period ratios output (must include PRIMARY/COMPARISON rows).
        comparison_enabled: Whether the comparison period is enabled for the page.
        currency_code: Currency code used to format amount tiles.
        thousands_separator: Thousands separator for formatted numbers ("," or " ").

    Tile config fields (layout TOML):
        label (str): Tile title shown in the UI.
        source (str): "measure" (default) or "ratio".
        key (str): Measure/ratio key to lookup in the corresponding DataFrame.
        format (str): "amount" | "percent" | "days" | "number"
        (passed to formatting helpers).
        tooltip_from (str): "", "measure_notes", or "ratio_notes".
        show_delta_abs (bool): Show absolute delta (primary - comparison).
        show_delta_pct (bool): Show relative delta percentage (delta / comparison).
        delta_good_direction (str): "up" (positive is good) or "down"
        (negative is good).

    Notes:
        - When comparison is disabled, delta is not displayed.
        - For percent tiles with abs-only delta, we display percentage points (pp).
    """
    if not tiles:
        return

    # cols = st.columns(4) if len(tiles) >= 4 else st.columns(max(1, len(tiles)))
    cols = st.columns(5)

    for i, tile in enumerate(tiles):
        t = _to_mapping(tile)

        label = t.get("label", "Metric")
        source = (t.get("source") or "measure").lower()
        key = t.get("key")
        fmt = t.get("format", "amount")
        tooltip_from = t.get("tooltip_from", "")
        help_text = ""

        # Optional direct tooltip override (used by Ratios page tiles).
        # If present, it wins over measure/ratio notes sourcing.
        tooltip_text = (t.get("tooltip_text") or "").strip()
        if tooltip_text:
            help_text = tooltip_text

        show_delta_abs = bool(t.get("show_delta_abs", True))
        show_delta_pct = bool(t.get("show_delta_pct", False))
        delta_good_direction = (t.get("delta_good_direction") or "up").lower()

        primary_val: Optional[float] = None
        comp_val: Optional[float] = None

        # Optional tooltip sourcing from compute notes
        # (kept outside TOML to avoid duplication).
        if not help_text:
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
                if comparison_enabled:
                    comp_val = _ratio_value(ratios_df, "COMPARISON", key)
            else:
                primary_val = _measure_value(measures_df, "PRIMARY", key)
                if comparison_enabled:
                    comp_val = _measure_value(measures_df, "COMPARISON", key)

        delta_abs, delta_pct = _compute_delta(primary_val, comp_val)

        # Streamlit only supports ONE delta string,
        # so we build a combined representation here.
        delta_str = None
        if comparison_enabled:
            # Percent tiles: abs-only delta should be shown in percentage points (pp)
            is_percent_fmt = (fmt or "").lower().strip() in {"percent", "%"}
            if is_percent_fmt and show_delta_abs and not show_delta_pct:
                delta_str = (
                    _format_pp(delta_abs, thousands_separator=thousands_separator)
                    if delta_abs is not None
                    else None
                )
            else:
                delta_str = _build_delta_string(
                    delta_abs=delta_abs,
                    delta_pct=delta_pct,
                    fmt=fmt,
                    show_abs=show_delta_abs,
                    show_pct=show_delta_pct,
                    currency_code=currency_code,
                    thousands_separator=thousands_separator,
                )

        # Keep a consistent tile height: when comparison is enabled but the delta
        # cannot be computed (e.g., missing value / division by zero), Streamlit
        # would hide the delta line if delta=None, shrinking the container.
        # We force a placeholder delta in that case.
        placeholder_delta = False
        if (
            comparison_enabled
            and (show_delta_abs or show_delta_pct)
            and delta_str is None
        ):
            delta_str = "—"
            placeholder_delta = True

        # Streamlit supports delta_color: normal / inverse / off
        # "down" means negative delta is good (green) => inverse

        # delta_color = "normal" if delta_good_direction == "up" else "inverse"
        base_delta_color = "normal" if delta_good_direction == "up" else "inverse"

        # Disable delta coloring when:
        # - we display a placeholder delta (no meaningful comparison)
        # - the delta is effectively zero (avoid useless arrow + colored background)
        eps = 1e-12

        is_zero_abs = (delta_abs is not None) and (abs(delta_abs) < eps)
        is_zero_pct = (delta_pct is not None) and (abs(delta_pct) < eps)

        # Determine if displayed deltas are "zero" given what is enabled for this tile
        if placeholder_delta:
            effective_delta_color = "off"
        else:
            # If only abs is shown -> abs zero => off
            # If only pct is shown -> pct zero => off
            # If both are shown -> both must be zero to turn off
            if show_delta_abs and show_delta_pct:
                is_effectively_zero = is_zero_abs and (is_zero_pct or delta_pct is None)
            elif show_delta_abs:
                is_effectively_zero = is_zero_abs
            elif show_delta_pct:
                is_effectively_zero = is_zero_pct
            else:
                is_effectively_zero = False

            effective_delta_color = (
                "off"
                if (comparison_enabled and is_effectively_zero)
                else base_delta_color
            )

        # If delta is neutral (gray), also disable the arrow to avoid misleading cues.
        effective_delta_arrow = "off" if effective_delta_color == "off" else "auto"

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
                    delta_color=effective_delta_color,
                    delta_arrow=effective_delta_arrow,
                    help=help_text,
                )
