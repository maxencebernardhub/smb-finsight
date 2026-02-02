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
- Compute and display the primary income statement and an optional secondary statement
  when configured for the selected standard (no comparison yet).
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
    """
    Render the Income Statement page (single statement and optional secondary
    statement, no comparison yet).
    """

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
        df_primary_all = pipe.primary_df
        df_secondary_all = pipe.secondary_df
    except Exception as exc:  # noqa: BLE001
        st.error(f"Failed to compute income statement: {exc}")
        df_primary_all = pd.DataFrame()
        df_secondary_all = pd.DataFrame()

    if df_primary_all.empty:
        st.info(
            ui.get(
                "msg_no_entries", "No accounting entries found for the selected period."
            )
        )
        return

    label = getattr(primary_period, "label", "PRIMARY")

    df_primary = df_primary_all
    if "period_label" in df_primary.columns:
        df_primary = df_primary[
            df_primary["period_label"].astype(str) == str(label)
        ].copy()
    if df_primary.empty:
        st.info(
            ui.get(
                "msg_no_entries", "No accounting entries found for the selected period."
            )
        )
        return

    df_secondary = None
    if df_secondary_all is not None and not df_secondary_all.empty:
        df_secondary = df_secondary_all
        if "period_label" in df_secondary.columns:
            df_secondary = df_secondary[
                df_secondary["period_label"].astype(str) == str(label)
            ].copy()
        if df_secondary.empty:
            df_secondary = None

    # Apply view-level filtering (shared with CLI)
    hide_zero = getattr(stmt_cfg, "hide_zero_lines_single_period", False)
    try:
        df_primary_view, warnings = build_statement_view(
            app_config=app_config,
            df_statement=df_primary,
            period=primary_period,
            view_level=view_level,
            hide_zero_lines=hide_zero,
            statement_role="primary",
        )
        for w in warnings:
            st.warning(w)

        df_secondary_view = None
        if df_secondary is not None:
            df_secondary_view, warnings2 = build_statement_view(
                app_config=app_config,
                df_statement=df_secondary,
                period=primary_period,
                view_level=view_level,
                hide_zero_lines=hide_zero,
                statement_role="secondary",
            )
            for w in warnings2:
                st.warning(w)

    except Exception as exc:  # noqa: BLE001
        st.warning(f"View filtering failed (showing full statement): {exc}")
        df_primary_view = df_primary
        df_secondary_view = df_secondary

    primary_title = getattr(
        app_config.standard_config, "primary_statement_label", ""
    ) or ui.get("label_primary_statement", "Income statement")
    secondary_title = getattr(
        app_config.standard_config, "secondary_statement_label", ""
    ) or ui.get("label_secondary_statement", "Secondary statement")

    st.space(size="small")

    display_mode = (
        str(getattr(stmt_cfg, "secondary_statement_display", "tabs") or "tabs")
        .strip()
        .lower()
    )
    if display_mode not in {"tabs", "stacked"}:
        st.warning(
            f"Invalid secondary_statement_display='{display_mode}', "
            f"falling back to 'tabs'."
        )
        display_mode = "tabs"

    if df_secondary_view is None:
        st.subheader(primary_title)
        render_statement_table(
            df_view=df_primary_view,
            ui=ui,
            stmt_cfg=stmt_cfg,
        )
    else:
        if display_mode == "stacked":
            st.subheader(primary_title)
            render_statement_table(
                df_view=df_primary_view,
                ui=ui,
                stmt_cfg=stmt_cfg,
            )

            st.space(size="small")
            st.subheader(secondary_title)
            render_statement_table(
                df_view=df_secondary_view,
                ui=ui,
                stmt_cfg=stmt_cfg,
            )
        else:
            tab1, tab2 = st.tabs([primary_title, secondary_title])
            with tab1:
                render_statement_table(
                    df_view=df_primary_view,
                    ui=ui,
                    stmt_cfg=stmt_cfg,
                )
            with tab2:
                render_statement_table(
                    df_view=df_secondary_view,
                    ui=ui,
                    stmt_cfg=stmt_cfg,
                )
