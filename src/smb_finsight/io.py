# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
I/O module for SMB FinSight.

This module handles reading accounting entries from a CSV file and normalizing
them into a simple, consistent structure suitable for aggregation by the engine.

Expected input formats
----------------------

Two canonical input formats are supported (column names are case-insensitive):

1) Debit / credit format
   ----------------------
       date, code, debit, credit, description

   - ``date``:        date of the entry (YYYY-MM-DD)
   - ``code``:        chart of accounts code (PCG)
   - ``debit``:       debit amount (positive number or 0)
   - ``credit``:      credit amount (positive number or 0)
   - ``description``: free text label for the entry

   The signed amount is computed as:

       amount = credit - debit

   so that:
   - expenses (normally in debit) produce negative amounts,
   - revenues (normally in credit) produce positive amounts.

2) Pre-computed signed amount format
   ---------------------------------
       date, code, amount, description

   - ``amount`` is a signed number (credit - debit) already computed upstream.

Label alias
-----------
The column ``label`` is accepted as an alias for ``description`` for backward
compatibility with older CSV examples. Internally, everything is exposed as
``description``.

Output schema
-------------
Regardless of the input format, this function returns a pandas DataFrame with
the following columns:

    - ``date``        (datetime64[ns])
    - ``code``        (str)
    - ``description`` (str)
    - ``amount``      (float, signed)

Any other columns present in the input file are ignored.

If the CSV structure does not match one of the supported formats, a clear
ValueError is raised.
"""

import os
from typing import Union

import pandas as pd


def read_accounting_entries(path: Union[str, "os.PathLike[str]"]) -> pd.DataFrame:
    """
    Read accounting entries from a CSV file and normalize them.

    Parameters
    ----------
    path:
        Path to the CSV file containing accounting entries.

    Supported input formats (case-insensitive column names)
    -------------------------------------------------------

    1) Debit / credit format
           date, code, debit, credit, description

    2) Signed amount format
           date, code, amount, description

    The column name ``label`` is accepted as an alias for ``description``.

    Returns
    -------
    pandas.DataFrame
        A DataFrame with exactly these columns:

            - date        (datetime64[ns])
            - code        (str)
            - description (str)
            - amount      (float, signed)

    Raises
    ------
    ValueError
        If the CSV does not contain one of the supported column sets or if
        numeric/date parsing fails.
    """

    # Read the CSV file
    df = pd.read_csv(path)

    # Normalize column names to lowercase (to make the check case-insensitive)
    df.columns = [c.lower().strip() for c in df.columns]
    cols = set(df.columns)

    # Backward compat: 'label' -> 'description' if needed
    if "label" in cols and "description" not in cols:
        df = df.rename(columns={"label": "description"})
        cols = set(df.columns)

    required_debit_credit = {"date", "code", "debit", "credit", "description"}
    required_amount = {"date", "code", "amount", "description"}

    # ----- Case 1: debit / credit format ------------------------------------
    if required_debit_credit.issubset(cols):
        d = df.copy()

        # Parse date strictly: invalid dates should fail loudly
        try:
            d["date"] = pd.to_datetime(d["date"], errors="raise")
        except Exception as exc:  # noqa: BLE001
            raise ValueError("Invalid values in 'date' column.") from exc

        # Numeric conversion for debit/credit
        for col in ("debit", "credit"):
            d[col] = pd.to_numeric(d[col], errors="coerce")

        if d[["debit", "credit"]].isna().any().any():
            raise ValueError("Invalid numeric values in 'debit'/'credit' columns.")

        # Compute signed amount
        d["amount"] = d["credit"] - d["debit"]

        out = d[["date", "code", "description", "amount"]].copy()
        out["description"] = out["description"].astype(str).fillna("")

        return out

    # ----- Case 2: signed amount format -------------------------------------
    if required_amount.issubset(cols):
        d = df.copy()

        try:
            d["date"] = pd.to_datetime(d["date"], errors="raise")
        except Exception as exc:  # noqa: BLE001
            raise ValueError("Invalid values in 'date' column.") from exc

        d["amount"] = pd.to_numeric(d["amount"], errors="coerce")
        if d["amount"].isna().any():
            raise ValueError("Invalid numeric values in 'amount' column.")

        out = d[["date", "code", "description", "amount"]].copy()
        out["description"] = out["description"].astype(str).fillna("")

        return out

    # ----- Invalid structure → raise with clear message ---------------------
    raise ValueError(
        "Invalid accounting_entries structure. Expected either:\n"
        "  - date, code, debit, credit, description\n"
        "  - date, code, amount, description\n"
        "(column names are case-insensitive; 'label' is accepted as an alias "
        "for 'description')."
    )
