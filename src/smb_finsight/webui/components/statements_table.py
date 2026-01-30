# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.


"""
Statements table renderer (WebUI).

This component:
- Builds display columns ("Line", "Amount") from a statement dataframe.
- Applies amount formatting rules (engine_signed vs traditional + parentheses).
- Applies level-based styling and negative amount styling.
- Renders a Streamlit dataframe with configurable headers.
"""

from collections.abc import Mapping
from typing import Any

import pandas as pd
import streamlit as st

from smb_finsight.webui.utils import _to_mapping


def render_statement_table(
    *,
    df_view: pd.DataFrame,
    ui: Mapping[str, Any],
    stmt_cfg: Any,
) -> None:
    """
    Render a single statement dataframe with styling.

    Args:
        df_view:
            Statement dataframe after view filtering (and sorting if desired),
            expected to contain at least: name, level, amount.
        ui:
            page.ui mapping (labels, headers).
        stmt_cfg:
            Parsed layout statements config (layout.statements in LayoutConfig).
            Used for amount_display_mode, negative_amount_indicator, legend_text.
    """
    ui_m: Mapping[str, Any] = _to_mapping(ui)

    if df_view.empty:
        st.info(
            ui_m.get(
                "msg_no_entries", "No accounting entries found for the selected period."
            )
        )
        return

    # Headers
    label_header_line = ui_m.get("label_header_line", "REVENUE / EXPENSE")
    label_header_amount = ui_m.get("label_header_amount", "$")

    # ---------------------------------------------------------------------
    # Indentation + amount formatting
    # ---------------------------------------------------------------------
    df = df_view.copy()

    # Indent labels based on hierarchy level
    def _indent_name(row: pd.Series) -> str:
        try:
            lvl = int(row.get("level", 0) or 0)
        except Exception:  # noqa: BLE001
            lvl = 0
        name = str(row.get("name", ""))
        return ("\u00a0" * 6 * max(lvl, 0)) + name

    df["Line"] = df.apply(_indent_name, axis=1)

    amounts = pd.to_numeric(df.get("amount", 0), errors="coerce").fillna(0.0)

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

    df["Amount"] = [
        _fmt_amount(float(a), bool(e < 0))
        for a, e in zip(shown_amount.tolist(), engine_amount.tolist())
    ]

    # ---------------------------------------------------------------------
    # Dataframe rendering (Streamlit + Styler)
    # ---------------------------------------------------------------------
    df_visible = df[["Line", "Amount"]].copy()

    lvl_s = pd.to_numeric(df.get("level", 0), errors="coerce").fillna(0).astype(int)
    eng_s = pd.to_numeric(df.get("amount", 0), errors="coerce").fillna(0.0)

    def _style_row(row: pd.Series) -> list[str]:
        """
        Return per-cell CSS styles for a row (Line, Amount).
        Uses lvl_s/eng_s aligned by index.
        """
        idx = row.name
        lvl = int(lvl_s.loc[idx]) if idx in lvl_s.index else 0
        eng_amt = float(eng_s.loc[idx]) if idx in eng_s.index else 0.0

        style_line: list[str] = []
        style_amt: list[str] = []

        # Level styles (keep exactly your current look)
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
            "Line": st.column_config.TextColumn(str(label_header_line), width="large"),
            "Amount": st.column_config.TextColumn(str(label_header_amount), width=None),
        },
    )

    legend_text = str(getattr(stmt_cfg, "legend_text", "") or "").strip()
    if display_mode == "traditional" and legend_text:
        st.caption(legend_text)
