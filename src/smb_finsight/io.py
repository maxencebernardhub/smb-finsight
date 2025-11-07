# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

import pandas as pd


def read_accounting_entries(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    cols = [c.lower().strip() for c in df.columns]
    df.columns = cols

    if {"code", "amount"}.issubset(set(cols)):
        # assume signed amounts already
        return df[["code", "amount"]].copy()

    if {"code", "debit", "credit"}.issubset(set(cols)):
        d = df.copy()
        for col in ["debit", "credit"]:
            d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0.0)
        d["amount"] = d["credit"] - d["debit"]
        return d[["code", "amount"]]

    raise ValueError(
        "accounting_entries must include either columns: (code, amount) OR "
        "(code, debit, credit)"
    )
