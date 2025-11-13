# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Account utilities for SMB FinSight.

This module contains helpers related to the chart of accounts (list of accounts),
which is a user-maintained CSV (e.g. data/accounts/pcg.csv).

Responsibilities:
- Load the list of accounts (account code + label) from CSV.
- Filter accounting entries to keep only those whose account codes exist in this list,
  now accepting entries that match the **closest known ancestor** by prefix.
  Entries are ignored only if **no** prefix of the code exists in the list.
"""

from typing import Optional

import pandas as pd


def load_list_of_accounts(path: str) -> pd.DataFrame:
    """Load the chart of accounts (list of accounts) from CSV.

    Expected structure
    ------------------
    The CSV must contain at least:
        - one column with the account code:
            'account_number', 'account' or 'code'
        - one column with the account label:
            'name', 'label' or 'description'

    Column names are matched case-insensitively and trimmed.

    Args:
        path: Path to the CSV file containing the chart of accounts.

    Returns:
        A DataFrame with exactly two columns:
            - 'account_number': account code as string
            - 'name': account label as string

    Raises:
        ValueError: if no suitable account code or label column can be found.
    """
    df = pd.read_csv(path)
    # Normalize column names: lowercase + stripped, to be robust to variations.
    col_map = {str(c).strip().lower(): c for c in df.columns}

    # Find the account code column.
    code_col_candidates = ["account_number", "account", "code"]
    code_col = None
    for cand in code_col_candidates:
        if cand in col_map:
            code_col = col_map[cand]
            break
    if code_col is None:
        raise ValueError(
            "Could not find an account code column in list_of_accounts file. "
            "Expected one of: 'account_number', 'account', 'code'."
        )

    # Find the account label column.
    name_col_candidates = ["name", "label", "description"]
    name_col = None
    for cand in name_col_candidates:
        if cand in col_map:
            name_col = col_map[cand]
            break
    if name_col is None:
        raise ValueError(
            "Could not find an account name/label column in list_of_accounts file. "
            "Expected one of: 'name', 'label', 'description'."
        )

    out = df[[code_col, name_col]].copy()
    out.columns = ["account_number", "name"]
    out["account_number"] = out["account_number"].astype(str).str.strip()
    out["name"] = out["name"].astype(str).str.strip()
    return out


# ---------------------------------------------------------------------------
# New logic: prefix-based resolution of known account roots
# ---------------------------------------------------------------------------


def _resolve_to_known_account(code: str, known_codes: set[str]) -> Optional[str]:
    """Return the closest known ancestor of a given account code.

    The matching rule is based on prefix containment:
    - '606300' → '6063' if that prefix exists in the list
    - '6065'   → '606'  if '606' exists
    - '600010' → '60'   if '60' exists
    - '123456' → None   if no prefix matches

    Args:
        code: Raw account code from an accounting entry.
        known_codes: Set of known account codes (from the chart of accounts).

    Returns:
        The most specific known prefix of the code, or None if no prefix exists.
    """
    s = str(code).strip()
    # Check progressively shorter prefixes until we find one
    for i in range(len(s), 0, -1):
        prefix = s[:i]
        if prefix in known_codes:
            return prefix
    return None


def filter_unknown_accounts(
    accounting_entries: pd.DataFrame, known_codes: set[str]
) -> pd.DataFrame:
    """Filter out accounting entries based on prefix-matching with the chart of
    accounts.

    Keeps an entry if:
      - its code is exactly present in the list of known accounts, or
      - it has a parent (ancestor) code that exists in the list (by prefix).

    Ignores an entry only if *no* prefix is found in the chart of accounts.
    In that case, the function prints:
        "Unknown account code XXX, ignored"

    Args:
        accounting_entries: DataFrame containing at least a 'code' column.
        known_codes: Set of valid account codes (from list_of_accounts).

    Returns:
        Filtered DataFrame including only entries that map to a known or
        ancestor account code.
    """
    df = accounting_entries.copy()
    df["code"] = df["code"].astype(str).str.strip()

    keep_mask = []
    for _, row in df.iterrows():
        code = row["code"]
        resolved = _resolve_to_known_account(code, known_codes)
        keep = resolved is not None
        keep_mask.append(keep)
        if not keep:
            print(f"Unknown account code {code}, ignored")

    return df[pd.Series(keep_mask, index=df.index)].copy()
