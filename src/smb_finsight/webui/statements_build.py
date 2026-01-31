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

from typing import Any

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


def build_statement_view(
    *,
    app_config: AppConfig,
    df_statement: pd.DataFrame,
    period: Any,
    view_level: str,
    hide_zero_lines: bool = False,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Build a statement dataframe ready for rendering for a given view level.

    Args:
        app_config: Application config (DB, standard_config, fiscal year).
        df_statement: Statement dataframe already filtered to a single period label.
        period: Period object for this dataframe (used for DB entry lookup in complete).
        view_level: simplified|regular|detailed|complete (case-insensitive).
        hide_zero_lines: Whether to hide zero-amount lines for single-period views.

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
        mapping_path = app_config.standard_config.income_statement_mapping
        if mapping_path is None:
            warnings.append(
                "No income statement mapping configured. Falling back to detailed view."
            )
            return out_base, warnings

        template = Template.from_csv(str(mapping_path))

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
