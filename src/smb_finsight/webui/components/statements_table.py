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


def _format_amount(
    v: float,
    *,
    amount_display_mode: str,
    negative_amount_indicator: str,
) -> str:
    """
    Format an amount according to statements rules.

    - "traditional": display abs(amount) by convention; negative shown by
    parentheses or minus.
    - "engine_signed": display signed values (minus sign when negative).

    negative_amount_indicator:
        - parentheses / minus / color / both
    Note: This helper only returns text; color styling is handled separately.
    """
    mode = str(amount_display_mode or "engine_signed").strip().lower()
    neg = str(negative_amount_indicator or "parentheses").strip().lower()

    # numeric safety
    try:
        x = float(v)
    except Exception:  # noqa: BLE001
        x = 0.0

    s = f"{abs(x):,.2f}"

    if mode == "traditional":
        if x < 0 and neg in {"parentheses", "both"}:
            return f"({s})"
        if x < 0 and neg == "minus":
            return f"-{s}"
        return s

    # engine_signed (or other): show minus for negative
    return f"-{s}" if x < 0 else s


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
    label_header_amount = ui_m.get("label_header_amount", "AMOUNT ($)")

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


def _indent_label(name: str, level: int) -> str:
    """Indent a statement line label according to hierarchy level."""
    return ("\u00a0" * 6 * max(int(level), 0)) + str(name)


def _fmt_traditional_amount(
    *,
    engine_value: float,
    neg_indicator: str,
) -> str:
    """
    Traditional amount formatting:
      - show abs(value)
      - parentheses if engine_value < 0 and neg_indicator includes parentheses/both
      - minus sign is NOT used here (traditional display convention).
    """
    try:
        eng = float(engine_value)
    except Exception:  # noqa: BLE001
        eng = 0.0
    shown = abs(eng)
    s = f"{shown:,.2f}"
    if eng < 0 and neg_indicator in {"parentheses", "both"}:
        return f"({s})"
    return s


def _fmt_signed_delta_with_plus(value: float) -> str:
    """
    Signed delta formatting used in traditional comparison mode:
      - keep sign (no parentheses, no color)
      - add explicit '+' for positive values
    Examples: -123.00, +123.00, 0.00
    """
    try:
        x = float(value)
    except Exception:  # noqa: BLE001
        x = 0.0
    s = f"{abs(x):,.2f}"
    if x > 0:
        return f"+{s}"
    if x < 0:
        return f"-{s}"
    return f"{0.0:,.2f}"


def _fmt_signed_pct_with_plus(value: float) -> str:
    """Same idea as _fmt_signed_delta_with_plus, but for percentage."""
    if value is None or pd.isna(value):
        return ""
    try:
        x = float(value)
    except Exception:  # noqa: BLE001
        return ""
    s = f"{abs(x):.1f}%"
    if x > 0:
        return f"+{s}"
    if x < 0:
        return f"-{s}"
    return "0.0%"


def render_statement_comparison_table(
    *,
    df_comp: pd.DataFrame,
    ui: Mapping[str, Any],
    stmt_cfg: Any,
    primary_label: str,
    comparison_label: str,
) -> None:
    """
    Render comparison mode as a single dataframe with 5 columns:
      Line | Primary | Comparison | Delta | Delta %

    Display rules:
      - Primary/Comparison:
          * 'traditional': abs() display with parentheses/colors driven by signed value
          * 'engine_signed': signed display (same as single-period)
      - Delta/Delta %:
          * always computed on signed amounts in builder
          * displayed as signed with explicit +/- prefix
              (no parentheses, no delta color)
    """
    ui_m: Mapping[str, Any] = _to_mapping(ui)

    if df_comp is None or df_comp.empty:
        st.info(
            ui_m.get(
                "msg_no_entries", "No accounting entries found for the selected period."
            )
        )
        return

    df = df_comp.copy()
    if "level" not in df.columns:
        df["level"] = 0
    if "name" not in df.columns:
        df["name"] = ""

    display_mode = (
        str(
            getattr(stmt_cfg, "amount_display_mode", "engine_signed") or "engine_signed"
        )
        .strip()
        .lower()
    )
    neg_indicator = (
        str(
            getattr(stmt_cfg, "negative_amount_indicator", "parentheses")
            or "parentheses"
        )
        .strip()
        .lower()
    )

    a = pd.to_numeric(df.get("amount_primary", 0.0), errors="coerce").fillna(0.0)
    b = pd.to_numeric(df.get("amount_comparison", 0.0), errors="coerce").fillna(0.0)
    d = pd.to_numeric(df.get("delta_abs", 0.0), errors="coerce").fillna(0.0)
    p = pd.to_numeric(
        df.get("delta_pct", pd.Series([float("nan")] * len(df))), errors="coerce"
    )

    col_a = str(primary_label or "PRIMARY")
    col_b = str(comparison_label or "COMPARISON")

    df["Line"] = df.apply(
        lambda r: _indent_label(r.get("name", ""), r.get("level", 0)), axis=1
    )

    if display_mode == "traditional":
        df[col_a] = [
            _fmt_traditional_amount(engine_value=float(v), neg_indicator=neg_indicator)
            for v in a.tolist()
        ]
        df[col_b] = [
            _fmt_traditional_amount(engine_value=float(v), neg_indicator=neg_indicator)
            for v in b.tolist()
        ]
        # Delta columns: signed with explicit '+' and no parentheses/colors.
        df["Δ"] = [_fmt_signed_delta_with_plus(float(v)) for v in d.tolist()]
        df["Δ %"] = [_fmt_signed_pct_with_plus(v) for v in p.tolist()]
    else:
        # engine_signed: amounts are shown signed; Delta columns also use
        # explicit '+' for positives.
        df[col_a] = [f"{float(v):,.2f}" for v in a.tolist()]
        df[col_b] = [f"{float(v):,.2f}" for v in b.tolist()]
        df["Δ"] = [_fmt_signed_delta_with_plus(float(v)) for v in d.tolist()]
        df["Δ %"] = [_fmt_signed_pct_with_plus(v) for v in p.tolist()]

    out_cols = ["Line", col_a, col_b, "Δ", "Δ %"]
    df_visible = df[out_cols].copy()

    lvl_s = pd.to_numeric(df.get("level", 0), errors="coerce").fillna(0).astype(int)

    # Only apply negative coloring in traditional mode for Primary/Comparison
    # (as requested).
    def _style_row(row: pd.Series) -> list[str]:
        idx = row.name
        lvl = int(lvl_s.loc[idx]) if idx in lvl_s.index else 0

        if lvl <= 1:
            base = "font-weight:700; background-color:rgba(148, 163, 184, 0.25);"
        elif lvl == 2:
            base = "font-weight:500; background-color:rgba(148, 163, 184, 0.15);"
        elif lvl == 3:
            base = "font-weight:400; background-color:rgba(148, 163, 184, 0.07);"
        else:
            base = "font-weight:300;"

        styles = [base] * len(out_cols)

        if display_mode == "traditional" and neg_indicator in {"color", "both"}:
            if float(a.loc[idx]) < 0:
                styles[out_cols.index(col_a)] += " color: rgba(185, 95, 93, 1.0);"
            if float(b.loc[idx]) < 0:
                styles[out_cols.index(col_b)] += " color: rgba(185, 95, 93, 1.0);"
            # IMPORTANT: no color for Delta columns in traditional (per your spec)

        return styles

    label_header_line = ui_m.get("label_header_line", "REVENUE / EXPENSE")

    styled = df_visible.style.apply(_style_row, axis=1)
    st.dataframe(
        styled,
        width="stretch",
        hide_index=True,
        height="content",
        column_config={
            "Line": st.column_config.TextColumn(str(label_header_line)),
            "Δ": st.column_config.TextColumn("Delta (Δ)"),
            "Δ %": st.column_config.TextColumn("Delta (Δ %)"),
        },
    )

    legend_text = str(getattr(stmt_cfg, "legend_text", "") or "").strip()
    if display_mode == "traditional" and legend_text:
        st.caption(legend_text)
