# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2026 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Statements view builder (WebUI).

This module contains statement-specific transformation logic that should not live
in Streamlit pages:
- apply view-level filters (simplified/regular/detailed)
- build "complete" view by injecting level-4 account rows (requires DB entries,
  chart of accounts and the mapping template)

No Streamlit calls here: we return warnings as strings so the UI can display them.
"""

from typing import Any, Literal

import numpy as np
import pandas as pd

from smb_finsight.accounts import filter_unknown_accounts, load_list_of_accounts
from smb_finsight.config import AppConfig
from smb_finsight.db import load_entries
from smb_finsight.mapping import Template
from smb_finsight.views import apply_view_level_filter, build_complete_view

_ALLOWED_VIEWS = {"simplified", "regular", "detailed", "complete"}


def hide_zero_lines_single_period(df: pd.DataFrame) -> pd.DataFrame:
    """
    Hide zero-amount lines for a single-period statement while preserving hierarchy.

    Rules:
    - Always keep level 0 and 1 rows (structural totals/sections).
    - For level >= 2: keep a row if:
        - its amount is non-zero, OR
        - any descendant row is kept (i.e., a non-zero exists somewhere in its subtree).
    Works for complete view too (levels 2/3/4 may be filtered).
    """
    if df.empty or "level" not in df.columns or "amount" not in df.columns:
        return df

    levels = pd.to_numeric(df["level"], errors="coerce").fillna(0).astype(int)
    amounts = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)

    keep = [False] * len(df)

    # stack[l] == whether there is any kept row in the subtree at level l or deeper
    stack: list[bool] = []

    for i in reversed(range(len(df))):
        lvl = int(levels.iat[i])
        amt = float(amounts.iat[i])

        # Descendant kept = any kept info deeper than current level
        descendant_kept = any(stack[lvl + 1 :]) if len(stack) > lvl + 1 else False

        # Trim stack to current level
        if len(stack) > lvl + 1:
            stack = stack[: lvl + 1]
        if len(stack) < lvl + 1:
            stack.extend([False] * (lvl + 1 - len(stack)))

        # Keep rule
        if lvl <= 1:
            k = True
        else:
            k = (amt != 0.0) or descendant_kept

        keep[i] = k

        # Propagate to parent: subtree under this level contains kept
        # if k or descendant_kept
        stack[lvl] = k or descendant_kept

    return df.loc[keep].copy()


def hide_zero_lines_comparison_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Hide zero lines for a comparison "columns" dataframe while preserving hierarchy.

    Expected columns:
        - level
        - filter_amount_primary (optional)
        - filter_amount_comparison (optional)
        - amount_primary (fallback)
        - amount_comparison (fallback)
        - delta_abs

    Behavior:
        - Always keep level 0 and 1 rows (structural totals/sections).
        - For level >= 2: keep if any of (primary, comparison, delta_abs) is non-zero
          OR if any descendant is kept (subtree contains something non-zero).
    """
    if df.empty or "level" not in df.columns:
        return df

    levels = pd.to_numeric(df["level"], errors="coerce").fillna(0).astype(int)
    # In comparison mode, we keep signed amounts for rendering.
    # For zero-line filtering, we use "what the user sees" in the amount columns:
    # abs() in traditional mode, signed amounts otherwise
    # (via filter_amount_* if present).

    a = pd.to_numeric(
        df.get("filter_amount_primary", df.get("amount_primary", 0.0)),
        errors="coerce",
    ).fillna(0.0)
    b = pd.to_numeric(
        df.get("filter_amount_comparison", df.get("amount_comparison", 0.0)),
        errors="coerce",
    ).fillna(0.0)
    d = pd.to_numeric(df.get("delta_abs", 0.0), errors="coerce").fillna(0.0)

    keep = [False] * len(df)
    stack: list[bool] = []

    for i in reversed(range(len(df))):
        lvl = int(levels.iat[i])

        descendant_kept = any(stack[lvl + 1 :]) if len(stack) > lvl + 1 else False

        if len(stack) > lvl + 1:
            stack = stack[: lvl + 1]
        if len(stack) < lvl + 1:
            stack.extend([False] * (lvl + 1 - len(stack)))

        if lvl <= 1:
            k = True
        else:
            non_zero = (
                (float(a.iat[i]) != 0.0)
                or (float(b.iat[i]) != 0.0)
                or (float(d.iat[i]) != 0.0)
            )
            k = non_zero or descendant_kept

        keep[i] = k
        stack[lvl] = k or descendant_kept

    return df.loc[keep].copy()


def build_statement_view(
    *,
    app_config: AppConfig,
    df_statement: pd.DataFrame,
    period: Any,
    view_level: str,
    hide_zero_lines: bool = False,
    statement_role: Literal["primary", "secondary"] = "primary",
) -> tuple[pd.DataFrame, list[str]]:
    """
    Build a statement dataframe ready for rendering for a given view level.

    Args:
        app_config: Application config (DB, standard_config, fiscal year).
        df_statement: Statement dataframe already filtered to a single period label.
        period: Period object for this dataframe (used for DB entry lookup in complete).
        view_level: simplified|regular|detailed|complete (case-insensitive).
        hide_zero_lines: Whether to hide zero-amount lines for single-period views.
        statement_role:
            Which statement this dataframe corresponds to:
            - "primary": uses standard_config.income_statement_mapping for complete view
            - "secondary": uses standard_config.secondary_mapping for complete view

    Returns:
        (df_view, warnings)
    """
    warnings: list[str] = []

    if df_statement is None or df_statement.empty:
        return pd.DataFrame(), warnings

    level = str(view_level or "regular").strip().lower()
    if level not in _ALLOWED_VIEWS:
        level = "regular"

    if level != "complete":
        # Delegate to shared view filter logic (CLI parity)
        df_out = apply_view_level_filter(df_statement, level)
        if "display_order" in df_out.columns:
            df_out = df_out.sort_values(["display_order"], kind="mergesort")

        if hide_zero_lines:
            df_out = hide_zero_lines_single_period(df_out)

        return df_out, warnings

    # --- Complete view ---------------------------------------------------
    # Build a stable detailed base (ensures ordering + expected columns)
    out_base = apply_view_level_filter(df_statement, "detailed")
    if "display_order" in out_base.columns:
        out_base = out_base.sort_values(["display_order"], kind="mergesort")

    if hide_zero_lines:
        out_base = hide_zero_lines_single_period(out_base)

    try:
        # Load accounting entries for this period
        tx_raw = load_entries(app_config.database, period.start, period.end)

        # If there are no entries (or missing schema), we cannot inject account rows.
        if (
            tx_raw is None
            or tx_raw.empty
            or "code" not in getattr(tx_raw, "columns", [])
        ):
            return out_base, warnings

        # Chart of accounts is required for account names
        coa_path = app_config.standard_config.chart_of_accounts
        if coa_path is None:
            warnings.append(
                "Complete view requires a chart of accounts. "
                "Falling back to detailed view."
            )
            return out_base, warnings

        accounts_df = load_list_of_accounts(coa_path)
        known_codes = set(accounts_df["account_number"])
        name_by_code = dict(zip(accounts_df["account_number"], accounts_df["name"]))

        # Filter unknown accounts (same behavior as CLI)
        tx = filter_unknown_accounts(tx_raw, known_codes)

        # Mapping template required to map account codes -> statement rows
        if statement_role == "secondary":
            mpath = app_config.standard_config.secondary_mapping
        else:
            mpath = app_config.standard_config.income_statement_mapping

        if mpath is None:
            warnings.append(
                "No mapping configured for complete view. Falling back to detailed view"
            )
            return out_base, warnings

        template = Template.from_csv(str(mpath))

        df_complete = build_complete_view(
            out_base=out_base,
            accounting_entries=tx,
            template=template,
            name_by_code=name_by_code,
        )

        if hide_zero_lines:
            df_complete = hide_zero_lines_single_period(df_complete)

        return df_complete, warnings
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"Complete view failed; falling back to detailed. ({exc})")
        return out_base, warnings


def build_statement_comparison_columns(
    *,
    df_primary_view: pd.DataFrame,
    df_comparison_view: pd.DataFrame,
    amount_display_mode: str,
    hide_zero_lines_in_comparison: bool,
) -> pd.DataFrame:
    """
    Build a single dataframe for comparison mode ("columns").

    Output columns (logical):
        - display_order (if available, for stable sorting)
        - id (if available, stable join key)
        - level, name, type
        - amount_primary (SIGNED)
        - amount_comparison (SIGNED)
        - delta_abs
        - delta_pct

    Delta rule (for ALL modes, including 'traditional'):
        delta_abs = amount_primary_signed - amount_comparison_signed
        delta_pct = (delta_abs / amount_comparison_signed) * 100

    Note:
        In 'traditional' display, primary/comparison amounts may be rendered as abs()
        with parentheses/colors based on the *signed* value. We preserve signed amounts
        here so rendering stays consistent with single-period mode.
    """
    if df_primary_view is None or df_primary_view.empty:
        return pd.DataFrame()
    if df_comparison_view is None or df_comparison_view.empty:
        return pd.DataFrame()

    mode = str(amount_display_mode or "engine_signed").strip().lower()
    traditional = mode == "traditional"

    # Prefer a stable join key
    if "id" in df_primary_view.columns and "id" in df_comparison_view.columns:
        key_cols = ["id"]
    else:
        # Fallback: best-effort structural matching
        key_cols = [
            c
            for c in ["display_order", "level", "name"]
            if c in df_primary_view.columns and c in df_comparison_view.columns
        ]
        if not key_cols:
            return pd.DataFrame()

    left = df_primary_view.copy()
    right = df_comparison_view.copy()

    l_amt = pd.to_numeric(left.get("amount", 0.0), errors="coerce").fillna(0.0)
    r_amt = pd.to_numeric(right.get("amount", 0.0), errors="coerce").fillna(0.0)

    # IMPORTANT:
    # - Keep signed amounts for rendering (negative formatting uses the sign).
    left["_amt_signed"] = l_amt
    right["_amt_signed"] = r_amt

    base_cols = [
        c for c in ["display_order", "id", "level", "name", "type"] if c in left.columns
    ]

    l_min = left[base_cols + ["_amt_signed"]].copy()
    r_min = right[base_cols + ["_amt_signed"]].copy()

    merged = l_min.merge(
        r_min,
        on=key_cols,
        how="outer",
        suffixes=("_primary", "_comparison"),
    )

    # Prefer PRIMARY structure fields; fallback to comparison
    if (
        "display_order_primary" in merged.columns
        or "display_order_comparison" in merged.columns
    ):
        merged["display_order"] = merged.get("display_order_primary").combine_first(
            merged.get("display_order_comparison")
        )
    for c in ["id", "level", "name", "type"]:
        if f"{c}_primary" in merged.columns or f"{c}_comparison" in merged.columns:
            merged[c] = merged.get(f"{c}_primary").combine_first(
                merged.get(f"{c}_comparison")
            )

    # Signed amounts used by the renderer (negatives must stay negative)
    merged["amount_primary"] = pd.to_numeric(
        merged.get("_amt_signed_primary", 0.0), errors="coerce"
    ).fillna(0.0)
    merged["amount_comparison"] = pd.to_numeric(
        merged.get("_amt_signed_comparison", 0.0), errors="coerce"
    ).fillna(0.0)

    # Delta is ALWAYS computed on signed amounts, including in 'traditional' mode.
    # Delta % uses the signed comparison amount as denominator:
    #   delta_pct = (delta_abs / amount_comparison_signed) * 100
    merged["delta_abs"] = merged["amount_primary"] - merged["amount_comparison"]

    denom = merged["amount_comparison"].replace(0.0, np.nan)
    merged["delta_pct"] = (merged["delta_abs"] / denom) * 100.0

    # For zero-line filtering, use "what the user sees" on the amount columns.
    # Traditional amounts are displayed as abs(), so filter on abs().
    if traditional:
        merged["filter_amount_primary"] = merged["amount_primary"].abs()
        merged["filter_amount_comparison"] = merged["amount_comparison"].abs()
    else:
        merged["filter_amount_primary"] = merged["amount_primary"]
        merged["filter_amount_comparison"] = merged["amount_comparison"]

    if "display_order" in merged.columns:
        merged = merged.sort_values(["display_order"], kind="mergesort")

    if hide_zero_lines_in_comparison:
        merged = hide_zero_lines_comparison_columns(merged)

    # Drop filter-only helpers (not part of the public output)
    for c in ["filter_amount_primary", "filter_amount_comparison"]:
        if c in merged.columns:
            merged.drop(columns=[c], inplace=True)

    cols_out = [
        c
        for c in [
            "display_order",
            "id",
            "level",
            "name",
            "type",
            "amount_primary",
            "amount_comparison",
            "delta_abs",
            "delta_pct",
        ]
        if c in merged.columns
    ]

    return merged[cols_out].copy()
