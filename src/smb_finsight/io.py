# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
I/O module for SMB FinSight.

This module handles reading accounting entries from a CSV file and normalizing
them into a simple, consistent structure suitable for aggregation by the engine.

Expected input formats
----------------------
1. Pre-computed amounts:
       code, amount
   → The file already contains signed amounts (credit - debit).

2. Debit/Credit form:
       code, debit, credit
   → The function computes `amount = credit - debit`.

Returned DataFrame
------------------
A pandas DataFrame with exactly two columns:
    - code   (string)
    - amount (float)

Notes
-----
- Column names are normalized to lowercase before checking.
- Any non-numeric debit/credit values are coerced to 0.0.
- No aggregation or business logic is performed here; this is a low-level I/O utility.
"""

import pandas as pd


def read_accounting_entries(path: str) -> pd.DataFrame:
    """Read a CSV file containing accounting entries and normalize columns.

    The CSV must include either:
      - columns: (code, amount)
        → assumes signed amounts are already provided,
      or
      - columns: (code, debit, credit)
        → computes `amount = credit - debit`.

    Args:
        path: Path to the CSV file to read.

    Returns:
        DataFrame with two columns:
            code   (str)
            amount (float)

    Raises:
        ValueError: If neither of the expected column combinations is found.
    """

    # Read the CSV file
    df = pd.read_csv(path)

    # Normalize column names to lowercase (to make the check case-insensitive)
    cols = [c.lower().strip() for c in df.columns]
    df.columns = cols

    # Case 1: file already contains signed amounts
    if {"code", "amount"}.issubset(set(cols)):
        # assume signed amounts already
        return df[["code", "amount"]].copy()

    # Case 2: file has separate debit/credit columns -> compute amount
    if {"code", "debit", "credit"}.issubset(set(cols)):
        d = df.copy()
        # Ensure numeric conversion (invalid or NaN → 0.0)
        for col in ["debit", "credit"]:
            d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0.0)
        d["amount"] = d["credit"] - d["debit"]
        return d[["code", "amount"]]

    # Invalid structure → raise with clear message
    raise ValueError(
        "accounting_entries must include either columns: (code, amount) OR "
        "(code, debit, credit)"
    )
