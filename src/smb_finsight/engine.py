# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Aggregation engine for SMB FinSight.

This module handles the transformation of raw accounting entries into
structured financial statements (Income Statement, SIG, or any other
statement defined by a mapping CSV).

It provides two core functions:

- ``aggregate()``:
    Takes normalized accounting entries (code, amount) and a Template
    built from a mapping CSV, and produces an aggregated statement with
    one row per mapping definition. Rows of type 'acc' aggregate account
    codes matching inclusion/exclusion patterns. Rows of type 'calc'
    compute values from formulas referencing other row IDs.

- ``build_canonical_measures()``:
    Extracts canonical financial measures from an aggregated statement
    based on the ``canonical_measure`` attribute defined in the mapping
    rows. This produces a dictionary of base measures that can be fed to
    the ratio and KPI engine (see ``ratios.py``).

The aggregation engine does not compute ratios, KPIs, or derived
measures. Its sole responsibility is to produce clean, structured data
from accounting entries, ready for higher-level financial analysis.
"""

from collections.abc import Mapping
from typing import Any, Optional

import pandas as pd

from .mapping import Template


def aggregate(accounting_entries: pd.DataFrame, template: Template) -> pd.DataFrame:
    """Aggregate accounting entries into statement rows.

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
        A pandas DataFrame representing the statement, with columns:
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


def build_canonical_measures(
    statement: pd.DataFrame,
    template: Template,
    extra_measures: Optional[Mapping[str, Any]] = None,
) -> dict[str, float]:
    """Build a dictionary of canonical measures from an aggregated statement.

    This helper takes the aggregated statement produced by ``aggregate()``
    and the corresponding Template, and extracts all rows that have a
    non-empty ``canonical_measure`` attribute. The resulting dictionary
    can then be used as the base set of measures for ratio/KPI computation.

    Args:
        statement:
            DataFrame returned by :func:`aggregate`, with at least:
            ``id`` (int) and ``amount`` (numeric) columns.
        template:
            Template instance used to build this statement. Its rows must
            define ``canonical_measure`` where applicable.
        extra_measures:
            Optional mapping of additional measures to inject into the
            result (for example: balance sheet inputs, HR inputs, period
            parameters). Values are converted to ``float`` when possible.

    Returns:
        A dictionary mapping canonical measure names to float values.
        If a canonical row id is missing from the statement, its value
        defaults to 0.0.
    """
    # Build a fast lookup: row id -> amount
    amount_by_id: dict[int, float] = {}
    if not statement.empty:
        # We tolerate missing columns but expect the standard output from aggregate().
        if "id" not in statement.columns or "amount" not in statement.columns:
            raise ValueError(
                "Statement DataFrame must contain 'id' and 'amount' columns."
            )

        for row in statement.itertuples(index=False):
            # Assuming the standard columns order from aggregate():
            # level, display_order, id, name, type, amount
            try:
                row_id = int(row.id)
                value = float(row.amount)
            except (AttributeError, TypeError, ValueError) as exc:
                raise ValueError(
                    "Invalid row structure in statement DataFrame for canonical "
                    "measure extraction."
                ) from exc

            amount_by_id[row_id] = value

    # Extract canonical measures from the template
    canonical: dict[str, float] = {}
    for row in template.rows:
        if not row.canonical_measure:
            continue

        value = amount_by_id.get(row.id, 0.0)
        # Defensive: treat NaN as 0.0
        try:
            if pd.isna(value):  # type: ignore[arg-type]
                value = 0.0
        except TypeError:
            # Non-numeric type, best effort: ignore and fall back to 0.0
            value = 0.0

        canonical[row.canonical_measure] = float(value)

    # Merge optional extra measures (balance sheet, HR, period, etc.)
    if extra_measures:
        for key, value in extra_measures.items():
            try:
                canonical[str(key)] = float(value)
            except (TypeError, ValueError):
                # Ignore values that cannot be converted to float
                continue

    return canonical
