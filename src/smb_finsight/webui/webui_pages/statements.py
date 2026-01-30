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

from smb_finsight.accounts import filter_unknown_accounts, load_list_of_accounts
from smb_finsight.config import AppConfig
from smb_finsight.db import load_entries
from smb_finsight.mapping import Template
from smb_finsight.multi_periods import compute_all_multi_period
from smb_finsight.views import apply_view_level_filter, build_complete_view
from smb_finsight.webui.layout import LayoutConfig, PageConfig
from smb_finsight.webui.period_ui import render_period_controls
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
        options = ["simplified", "regular", "detailed", "complete"]

        raw_default = (_get(page, "default_view", "") or "regular").strip().lower()
        default = raw_default if raw_default in options else "regular"
        default_idx = options.index(default)

        view_labels = _to_mapping(ui.get("view_labels", {}))

        def _fmt(v: str) -> str:
            return str(view_labels.get(v, v.capitalize()))

        return st.selectbox(
            ui.get("label_view", "View level"),
            options=options,
            index=default_idx,
            format_func=_fmt,
            help=ui.get(
                "help_view", "Controls how much detail is shown in the statement."
            ),
        )

    # ---------------------------------------------------------------------
    # Period controls (PRIMARY only for this iteration)
    # ---------------------------------------------------------------------
    selection = render_period_controls(
        page=page,
        app_config=app_config,
        allow_secondary_period=False,  # step-1 policy
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
        statements_mp, _, _ = compute_all_multi_period(
            app_config=app_config,
            standard_config=app_config.standard_config,
            periods=[primary_period],
            ratios_level="full",  # UI policy
        )
        df = statements_mp.primary
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
        if view_level == "complete":
            # 1) Build a stable "detailed" base (harmonized display_order + columns)
            out_base = apply_view_level_filter(df, "detailed")

            # 2) Load accounting entries for the selected period from the DB
            tx_raw = load_entries(
                app_config.database, primary_period.start, primary_period.end
            )

            # 3) Chart of accounts required to display account names
            coa_path = app_config.standard_config.chart_of_accounts
            if coa_path is None:
                st.warning(
                    "Complete view requires a chart of accounts. "
                    "Falling back to detailed view."
                )
                df_view = out_base
            else:
                accounts_df = load_list_of_accounts(coa_path)
                known_codes = set(accounts_df["account_number"])
                name_by_code = dict(
                    zip(accounts_df["account_number"], accounts_df["name"])
                )

                # Filter unknown accounts (same behavior as CLI)
                tx = filter_unknown_accounts(tx_raw, known_codes)

                # 4) Template required to map account codes to statement rows
                mapping_path = app_config.standard_config.income_statement_mapping
                if mapping_path is None:
                    st.warning(
                        "No income statement mapping configured. "
                        "Falling back to detailed view."
                    )
                    df_view = out_base
                else:
                    template = Template.from_csv(str(mapping_path))

                    # 5) Build complete view (inserts level-4 account rows)
                    df_view = build_complete_view(
                        out_base=out_base,
                        accounting_entries=tx,
                        template=template,
                        name_by_code=name_by_code,
                    )
        else:
            df_view = apply_view_level_filter(df, view_level)

    except Exception as exc:  # noqa: BLE001
        st.warning(f"View filtering failed (showing full statement): {exc}")
        df_view = df

    # Sort deterministically
    if view_level != "complete" and "display_order" in df_view.columns:
        df_view = df_view.sort_values(["display_order"], kind="mergesort")

    # Indent labels based on hierarchy level
    def _indent_name(row: pd.Series) -> str:
        try:
            lvl = int(row.get("level", 0) or 0)
        except Exception:  # noqa: BLE001
            lvl = 0
        name = str(row.get("name", ""))
        return ("\u00a0" * 6 * max(lvl, 0)) + name

    df_view = df_view.copy()
    df_view["Line"] = df_view.apply(_indent_name, axis=1)

    # Amount formatting (minimal: engine_signed vs traditional)
    amounts = pd.to_numeric(df_view.get("amount", 0), errors="coerce").fillna(0.0)
    display_mode = (
        str(getattr(stmt_cfg, "amount_display_mode", "engine_signed")).strip().lower()
    )
    neg_indicator = (
        str(getattr(stmt_cfg, "negative_amount_indicator", "parentheses"))
        .strip()
        .lower()
    )

    engine_amount = amounts
    shown_amount = (
        engine_amount.abs() if display_mode == "traditional" else engine_amount
    )

    def _fmt_amount(val: float, is_negative_engine: bool) -> str:
        s = f"{val:,.2f}"
        if (
            display_mode == "traditional"
            and is_negative_engine
            and neg_indicator in {"parentheses", "both"}
        ):
            return f"({s})"
        return s

    df_view["Amount"] = [
        _fmt_amount(float(a), bool(e < 0))
        for a, e in zip(shown_amount.tolist(), engine_amount.tolist())
    ]

    st.space(size="small")
    st.subheader(ui.get("label_primary_statement", "Income statement"))

    label_header_line = ui.get("label_header_line", "REVENUE / EXPENSE")
    label_header_amount = ui.get("label_header_amount", "$")

    # --- DataFrame rendering (Streamlit + Styler) ------------------------------

    # Keep only visible columns for the dataframe itself
    df_visible = df_view[["Line", "Amount"]].copy()

    # Keep engine-signed amount + level in side arrays (aligned on df_visible index)
    lvl_s = (
        pd.to_numeric(df_view.get("level", 0), errors="coerce").fillna(0).astype(int)
    )
    eng_s = pd.to_numeric(df_view.get("amount", 0), errors="coerce").fillna(0.0)

    def _style_row(row: pd.Series) -> list[str]:
        """
        Return per-cell CSS styles for a row (Line, Amount).
        Uses lvl_s/eng_s aligned by index, because df_visible doesn't carry them.
        """
        idx = row.name
        lvl = int(lvl_s.loc[idx]) if idx in lvl_s.index else 0
        eng_amt = float(eng_s.loc[idx]) if idx in eng_s.index else 0.0

        style_line: list[str] = []
        style_amt: list[str] = []

        # Typography by level (best effort)
        if lvl <= 1:
            base = "font-weight:700; background-color:rgba(148, 163, 184, 0.25);"
            style_line.append(base)
            style_amt.append(base)
        elif lvl == 2:
            base = "font-weight:500; background-color:rgba(148, 163, 184, 0.15);"
            style_line.append(base)
            style_amt.append(base)
        elif lvl == 3:
            base = "font-weight:400; background-color:rgba(148, 163, 184, 0.07);"
            style_line.append(base)
            style_amt.append(base)
        else:
            base = "font-weight:300;"
            style_line.append(base)
            style_amt.append(base)

        # Negative indicator: Amount font color (traditional only)
        if (
            display_mode == "traditional"
            and neg_indicator in {"color", "both"}
            and eng_amt < 0
        ):
            style_amt.append("color: rgba(185, 95, 93, 1.0);")

        return [" ".join(style_line), " ".join(style_amt)]

    styled = df_visible.style.apply(_style_row, axis=1, subset=["Line", "Amount"])

    st.dataframe(
        styled,
        width="stretch",
        hide_index=True,
        height="content",
        column_config={
            "Line": st.column_config.TextColumn(label_header_line, width="large"),
            "Amount": st.column_config.TextColumn(label_header_amount, width=None),
        },
    )

    legend_text = str(getattr(stmt_cfg, "legend_text", "") or "").strip()
    if display_mode == "traditional" and legend_text:
        st.caption(legend_text)
