# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Income Statement page (WebUI).

This module intentionally stays *thin*: it orchestrates layout + user selections
and relies on shared helpers for period selection and core computations.

Step 1 scope:
- Render period controls (PRIMARY only).
- Render a view-level selector in the third slot (column 3).
- Compute and display ONE primary income statement (no comparison, no secondary yet).
"""

from collections.abc import Mapping
from typing import Any

import pandas as pd
import streamlit as st

from smb_finsight.config import AppConfig
from smb_finsight.webui.components.statements_table import render_statement_table
from smb_finsight.webui.components.view_level import render_view_level_control
from smb_finsight.webui.layout import LayoutConfig, PageConfig
from smb_finsight.webui.period_ui import render_period_controls
from smb_finsight.webui.pipeline import run_statements_pipeline
from smb_finsight.webui.statements_build import build_statement_view
from smb_finsight.webui.utils import _get, _to_mapping


def render(app_config: AppConfig, layout: LayoutConfig, page: PageConfig) -> None:
    """Render the Income Statement page (single statement, no comparison yet)."""

    st.title(_get(page, "title", "Income Statement"))

    ui: Mapping[str, Any] = _to_mapping(_get(page, "ui", {}))
    stmt_cfg = layout.statements

    # ---------------------------------------------------------------------
    # Third-slot control: View level (returns the selected value)
    # ---------------------------------------------------------------------
    def _render_view_control() -> str:
        return render_view_level_control(page=page)

    # ---------------------------------------------------------------------
    # Period controls (PRIMARY only for this iteration)
    # ---------------------------------------------------------------------
    selection = render_period_controls(
        page=page,
        app_config=app_config,
        allow_secondary_period=page.allow_secondary_period,
        show_granularity=False,
        third_slot_renderer=_render_view_control,  # returns the view level
    )

    primary_period = selection.primary_period
    view_level = str(selection.third_slot_value or "regular").strip().lower()

    allowed_views = {"simplified", "regular", "detailed", "complete"}
    if view_level not in allowed_views:
        view_level = "regular"

    # ---------------------------------------------------------------------
    # Compute statement (single period)
    # ---------------------------------------------------------------------
    try:
        pipe = run_statements_pipeline(
            app_config=app_config,
            primary_period=primary_period,
            comparison_period=None,  # step 1: no comparison yet
        )
        df = pipe.primary_df
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to compute income statement: {exc}")
        df = pd.DataFrame()

    if df.empty:
        st.info(
            ui.get(
                "msg_no_entries", "No accounting entries found for the selected period."
            )
        )
        return

    label = getattr(primary_period, "label", "PRIMARY")
    if "period_label" in df.columns:
        df = df[df["period_label"].astype(str) == str(label)]
    if df.empty:
        st.info(
            ui.get(
                "msg_no_entries", "No accounting entries found for the selected period."
            )
        )
        return

    # Apply view-level filtering (shared with CLI)
    try:
        df_view, warnings = build_statement_view(
            app_config=app_config,
            df_statement=df,
            period=primary_period,
            view_level=view_level,
        )
        for w in warnings:
            st.warning(w)

    except Exception as exc:  # noqa: BLE001
        st.warning(f"View filtering failed (showing full statement): {exc}")
        df_view = df

    st.space(size="small")
    st.subheader(ui.get("label_primary_statement", "Income statement"))

    render_statement_table(
        df_view=df_view,
        ui=ui,
        stmt_cfg=stmt_cfg,
    )
