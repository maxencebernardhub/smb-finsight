# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Income Statement page (WebUI).

This module intentionally stays *thin*: it orchestrates layout + user selections
and relies on shared helpers for period selection and core computations.

Step scope:
- Render period controls (primary + optional comparison period).
- Render a view-level selector (third slot).
- Compute the primary income statement and optional secondary statement.
- If comparison is enabled, render a single comparison table ("columns" mode):
  Line | Primary | Comparison | Delta | Delta %
  where delta values are computed on signed amounts.
"""

from collections.abc import Mapping
from typing import Any

import pandas as pd
import streamlit as st

from smb_finsight.config import AppConfig
from smb_finsight.webui.components.statements_table import (
    render_statement_comparison_table,
    render_statement_table,
)
from smb_finsight.webui.components.view_level import render_view_level_control
from smb_finsight.webui.layout import LayoutConfig, PageConfig
from smb_finsight.webui.period_ui import render_period_controls
from smb_finsight.webui.pipeline import run_statements_pipeline
from smb_finsight.webui.statements_build import (
    build_statement_comparison_columns,
    build_statement_view,
)
from smb_finsight.webui.utils import _get, _to_mapping


def render(app_config: AppConfig, layout: LayoutConfig, page: PageConfig) -> None:
    """
    - Single-period mode: renders the statement and optional secondary statement.
    - Comparison mode (when enabled): renders a single comparison dataframe with
      5 columns: Line | Primary | Comparison | Δ | Δ %.
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
    # Period controls (primary + optional comparison period)
    # ---------------------------------------------------------------------
    selection = render_period_controls(
        page=page,
        app_config=app_config,
        allow_secondary_period=page.allow_secondary_period,
        show_granularity=False,
        third_slot_renderer=_render_view_control,  # returns the view level
    )

    primary_period = selection.primary_period
    comparison_period = selection.comparison_period
    comparison_active = bool(
        selection.comparison_enabled and comparison_period is not None
    )
    view_level = str(selection.third_slot_value or "regular").strip().lower()

    allowed_views = {"simplified", "regular", "detailed", "complete"}
    if view_level not in allowed_views:
        view_level = "regular"

    # ---------------------------------------------------------------------
    # Compute statements via pipeline (primary + optional secondary)
    # ---------------------------------------------------------------------
    try:
        pipe = run_statements_pipeline(
            app_config=app_config,
            primary_period=primary_period,
            comparison_period=comparison_period if comparison_active else None,
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
    hide_zero_single = bool(getattr(stmt_cfg, "hide_zero_lines_single_period", False))
    hide_zero_comp = bool(getattr(stmt_cfg, "hide_zero_lines_in_comparison", True))
    amount_display_mode = (
        str(
            getattr(stmt_cfg, "amount_display_mode", "engine_signed") or "engine_signed"
        )
        .strip()
        .lower()
    )

    # ---------------------------------------------------------------------
    # Build views for primary period
    # ---------------------------------------------------------------------

    try:
        df_primary_view, warnings = build_statement_view(
            app_config=app_config,
            df_statement=df_primary,
            period=primary_period,
            view_level=view_level,
            # In comparison mode, hide-zero is applied jointly after merge.
            hide_zero_lines=(hide_zero_single if not comparison_active else False),
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
                hide_zero_lines=(hide_zero_single if not comparison_active else False),
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

    # ---------------------------------------------------------------------
    # Rendering helpers: single-period OR comparison ("columns")
    # ---------------------------------------------------------------------
    def _render_primary_single() -> None:
        st.subheader(primary_title)
        render_statement_table(df_view=df_primary_view, ui=ui, stmt_cfg=stmt_cfg)

    def _render_secondary_single() -> None:
        if df_secondary_view is None:
            return
        if display_mode == "stacked":
            st.space(size="small")
            st.subheader(secondary_title)
            render_statement_table(df_view=df_secondary_view, ui=ui, stmt_cfg=stmt_cfg)
        else:
            tab1, tab2 = st.tabs([primary_title, secondary_title])
            with tab1:
                render_statement_table(
                    df_view=df_primary_view, ui=ui, stmt_cfg=stmt_cfg
                )
            with tab2:
                render_statement_table(
                    df_view=df_secondary_view, ui=ui, stmt_cfg=stmt_cfg
                )

    def _render_primary_comparison(df_comp_columns: pd.DataFrame) -> None:
        st.subheader(primary_title)
        render_statement_comparison_table(
            df_comp=df_comp_columns,
            ui=ui,
            stmt_cfg=stmt_cfg,
            primary_label=(
                selection.primary_preset_label
                or getattr(primary_period, "label", "PRIMARY")
            ),
            comparison_label=(
                selection.comparison_preset_label
                or getattr(comparison_period, "label", "COMPARISON")
            ),
        )

    def _render_secondary_comparison(df_comp_columns: pd.DataFrame) -> None:
        if df_secondary_view is None:
            return
        if display_mode == "stacked":
            st.space(size="small")
            st.subheader(secondary_title)
            render_statement_comparison_table(
                df_comp=df_comp_columns,
                ui=ui,
                stmt_cfg=stmt_cfg,
                primary_label=(
                    selection.primary_preset_label
                    or getattr(primary_period, "label", "PRIMARY")
                ),
                comparison_label=(
                    selection.comparison_preset_label
                    or getattr(comparison_period, "label", "COMPARISON")
                ),
            )

    # ---------------------------------------------------------------------
    # Single-period rendering
    # ---------------------------------------------------------------------

    if not comparison_active:
        if df_secondary_view is None:
            _render_primary_single()
        else:
            # preserve existing behavior
            if display_mode == "stacked":
                _render_primary_single()
                _render_secondary_single()
            else:
                _render_secondary_single()
        return

    # ---------------------------------------------------------------------
    # Comparison rendering
    # ---------------------------------------------------------------------
    comp_label = getattr(comparison_period, "label", "COMPARISON")
    df_comp_primary = df_primary_all
    if "period_label" in df_comp_primary.columns:
        df_comp_primary = df_comp_primary[
            df_comp_primary["period_label"].astype(str) == str(comp_label)
        ].copy()

    if df_comp_primary.empty:
        st.warning(
            "Comparison is enabled but no statement data "
            "was found for the comparison period."
        )
        _render_primary_single()
        if df_secondary_view is not None and display_mode == "stacked":
            _render_secondary_single()
        return

    df_comp_primary_view, warnings_c = build_statement_view(
        app_config=app_config,
        df_statement=df_comp_primary,
        period=comparison_period,
        view_level=view_level,
        hide_zero_lines=False,
        statement_role="primary",
    )
    for w in warnings_c:
        st.warning(w)

    df_primary_comp_columns = build_statement_comparison_columns(
        df_primary_view=df_primary_view,
        df_comparison_view=df_comp_primary_view,
        amount_display_mode=amount_display_mode,
        hide_zero_lines_in_comparison=hide_zero_comp,
    )

    # Secondary (if configured)
    df_secondary_comp_columns = pd.DataFrame()
    if (
        df_secondary_all is not None
        and not df_secondary_all.empty
        and df_secondary_view is not None
    ):
        df_comp_secondary = df_secondary_all
        if "period_label" in df_comp_secondary.columns:
            df_comp_secondary = df_comp_secondary[
                df_comp_secondary["period_label"].astype(str) == str(comp_label)
            ].copy()

        if not df_comp_secondary.empty:
            df_comp_secondary_view, warnings_s = build_statement_view(
                app_config=app_config,
                df_statement=df_comp_secondary,
                period=comparison_period,
                view_level=view_level,
                hide_zero_lines=False,
                statement_role="secondary",
            )
            for w in warnings_s:
                st.warning(w)

            df_secondary_comp_columns = build_statement_comparison_columns(
                df_primary_view=df_secondary_view,
                df_comparison_view=df_comp_secondary_view,
                amount_display_mode=amount_display_mode,
                hide_zero_lines_in_comparison=hide_zero_comp,
            )

    # Render (preserve secondary display mode)
    if df_secondary_view is None:
        _render_primary_comparison(df_primary_comp_columns)
    else:
        if display_mode == "stacked":
            _render_primary_comparison(df_primary_comp_columns)
            _render_secondary_comparison(df_secondary_comp_columns)
        else:
            # tabs: use the two precomputed dfs
            tab1, tab2 = st.tabs([primary_title, secondary_title])
            with tab1:
                render_statement_comparison_table(
                    df_comp=df_primary_comp_columns,
                    ui=ui,
                    stmt_cfg=stmt_cfg,
                    primary_label=(
                        selection.primary_preset_label
                        or getattr(primary_period, "label", "PRIMARY")
                    ),
                    comparison_label=(
                        selection.comparison_preset_label
                        or getattr(comparison_period, "label", "COMPARISON")
                    ),
                )
            with tab2:
                render_statement_comparison_table(
                    df_comp=df_secondary_comp_columns
                    if (not df_secondary_comp_columns.empty)
                    else pd.DataFrame(),
                    ui=ui,
                    stmt_cfg=stmt_cfg,
                    primary_label=(
                        selection.primary_preset_label
                        or getattr(primary_period, "label", "PRIMARY")
                    ),
                    comparison_label=(
                        selection.comparison_preset_label
                        or getattr(comparison_period, "label", "COMPARISON")
                    ),
                )
