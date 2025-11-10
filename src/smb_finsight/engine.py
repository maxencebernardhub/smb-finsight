# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Aggregation engine for SMB FinSight.

This module contains the core logic that:
1) takes normalized accounting entries (code, amount),
2) uses a Template (mapping rules) to assign each entry to one or more rows,
3) computes totals per row,
4) evaluates formula rows (e.g. '=1+2', '=SUM(7,14)'),
5) returns a flat DataFrame representing the income statement.

The actual mapping rules (which accounts go to which rows, and which formulas
are used) are defined in `mapping.Template` and read from CSV files.
"""

import pandas as pd

from .mapping import Template


def aggregate(accounting_entries: pd.DataFrame, template: Template) -> pd.DataFrame:
    """Aggregate accounting entries into income-statement rows.

    This function is the central step of the pipeline:
      - Input: a DataFrame with columns:
            code   (str)
            amount (float)
        where `amount` is already normalized (credit - debit).
      - Template: a `Template` instance built from a mapping CSV.
      - Output: a DataFrame with one row per mapping row, including:
            level, display_order, id, name, type, amount

    Steps:
        1. Initialize an amount bucket for each template row id.
        2. For each accounting entry, find matching row IDs and add the amount.
        3. For rows of type 'calc', compute their value using formulas that
           reference other row IDs.
        4. Build the final DataFrame sorted by (level, display_order).

    Args:
        accounting_entries: Normalized accounting entries (code, amount).
        template: Mapping/template describing which accounts feed which rows,
                  and how formula rows should be computed.

    Returns:
        A pandas DataFrame representing the income statement, with columns:
            level, display_order, id, name, type, amount
        `amount` is rounded to 2 decimal places.
    """

    """Aggregate accounting entries into income-statement rows.

    This function is the central step of the pipeline:
      - Input: a DataFrame with columns:
            code   (str)
            amount (float)
        where `amount` is already normalized (credit - debit).
      - Template: a `Template` instance built from a mapping CSV.
      - Output: a DataFrame with one row per mapping row, including:
            level, display_order, id, name, type, amount

    Steps:
        1. Initialize an amount bucket for each template row id.
        2. For each accounting entry, find matching row IDs and add the amount.
        3. For rows of type 'calc', compute their value using formulas that
           reference other row IDs.
        4. Build the final DataFrame sorted by (level, display_order).

    Args:
        accounting_entries: Normalized accounting entries (code, amount).
        template: Mapping/template describing which accounts feed which rows,
                  and how formula rows should be computed.

    Returns:
        A pandas DataFrame representing the income statement, with columns:
            level, display_order, id, name, type, amount
        `amount` is rounded to 2 decimal places.
    """

    # 1) Initialize an amount accumulator for every row id in the template.
    #    This ensures that even rows with no matching transactions appear
    #    with an amount of 0.0 in the final output.
    amounts: dict[int, float] = {r.id: 0.0 for r in template.rows}

    # 2) Classify each accounting entry into zero, one or multiple rows.
    #    For each entry:
    #      - use the template to determine which rows it contributes to,
    #      - add its amount to each target row's accumulator.
    for _, t in accounting_entries.iterrows():
        code = str(t["code"])
        amt = float(t["amount"])
        row_ids = template.match_rows_for_code(code)
        for rid in row_ids:
            amounts[rid] += amt

    # 3) Compute formula rows ('calc' type) using the current amounts.
    #    Formulas can reference other rows by id, or use SUM(...).
    #    The template is responsible for interpreting the formula.
    for r in template.rows:
        if r.type == "calc":
            amounts[r.id] = template.calc_formula(r.id, amounts)

    # 4) Build the final output structure, ordered by level and display_order.
    out = []
    for r in sorted(template.rows, key=lambda x: (x.level, x.display_order)):
        out.append(
            {
                "level": r.level,
                "display_order": r.display_order,
                "id": r.id,
                "name": r.name,
                "type": r.type,
                "amount": round(amounts.get(r.id, 0.0), 2),
            }
        )
    return pd.DataFrame(out)
