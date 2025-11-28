# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Core financial aggregation engine for SMB FinSight.

This module provides the core logic used to compute financial statements
(income statement, optional secondary statement such as SIG), canonical
measures, derived measures (via ratios.py), and helper metadata associated
with canonical measures.

The engine orchestrates three main responsibilities:

1. Statement aggregation
   ----------------------
   The `aggregate()` function computes the financial statements for a
   given period by:
   - loading accounting entries from the database,
   - matching them against a Template (mapping) definition,
   - evaluating 'acc' rows (account aggregations),
   - evaluating 'calc' rows (formulas based on other rows),
   - producing a long-format DataFrame with the final statement lines.

   Statements can include:
   - a primary statement (e.g. Income Statement),
   - an optional secondary statement (e.g. French PCG "SIG").

2. Canonical measures
   -------------------
   Some statement rows may define a "canonical_measure" in the mapping
   CSV. These measures represent standardized high-level financial metrics
   (e.g. 'revenue', 'gross_margin', 'operating_expenses').

   The canonical values are extracted via:
       build_canonical_measures(template, values_by_row_id)
   which returns a dictionary {measure_key -> float}.

   Metadata associated with canonical measures (human-readable label,
   unit, notes, etc.) is provided by:
       build_canonical_measures_metadata(template)
   which returns a dictionary {measure_key -> MeasureMeta}.

   This metadata is later used by higher-level modules such as
   `multi_periods.py` and the upcoming Web UI, enabling a richer
   presentation layer.

3. Derived measures & ratios (in conjunction with ratios.py)
   ----------------------------------------------------------
   Canonical measures can be complemented by "derived measures" defined
   in ratios TOML files. These are computed from:
       compute_derived_measures(base_measures, rules_file)

   Ratios (profitability, liquidity, leverage, etc.) are computed in
   `ratios.py` using both canonical and derived measures. The engine
   itself remains focused on raw aggregation and canonical measure
   extraction.

Key components
--------------
- Template :
    Mapping definition (CSV) describing how accounting entries should be
    aggregated into statement rows.

- MeasureMeta :
    Dataclass providing metadata for canonical measures, used by the
    Web UI and multi-period analysis logic.

- build_canonical_measures_metadata(template) :
    Extracts metadata (label, unit, notes) for canonical measures defined
    in a Template.

Notes
-----
This module intentionally does not handle multi-period logic or derived
measure metadata. Those responsibilities belong respectively to:
- multi_periods.py : orchestration of statements/measures/ratios over
  multiple periods.
- ratios.py        : metadata extraction and computation of derived
  measures and ratios.

The division of responsibilities keeps the engine minimal, predictable,
and reusable in both CLI and Web UI contexts.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Optional

import pandas as pd

from .mapping import Template

# ---------------------------------------------------------------------------
# Metadata for canonical measures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasureMeta:
    """
    Metadata associated with a canonical measure.

    Attributes
    ----------
    key :
        Unique identifier of the canonical measure (e.g. 'revenue', 'ebe').
    label :
        Human-readable label for display (coming from the mapping 'name' column).
    unit :
        Unit hint (e.g. 'amount', 'percent', 'days').
        Canonical measures produced by the engine are all monetary amounts.
    notes :
        Optional notes coming from the mapping 'notes' column.
    kind :
        Either 'canonical' (from the statement mapping) or 'extra'
        (reserved for future use).
    """

    key: str
    label: str
    unit: str
    notes: str
    kind: str = "canonical"


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


def build_canonical_measures_metadata(template: Template) -> dict[str, MeasureMeta]:
    """
    Build metadata for canonical measures defined in a Template.

    Canonical measures are defined in the mapping CSV via the column
    'canonical_measure'. Each mapping row may define at most one canonical
    measure. The metadata returned here is based on:

    - key   → the value of 'canonical_measure'
    - label → the 'name' column of the row
    - unit  → always 'amount' for canonical measures (monetary amounts)
    - notes → content of the 'notes' column (may be empty)
    - kind  → 'canonical'

    Parameters
    ----------
    template :
        A Template object whose rows have already been parsed by mapping.py.

    Returns
    -------
    dict[str, MeasureMeta]
        Dictionary mapping canonical measure keys to their metadata.

    Raises
    ------
    ValueError
        If the same canonical measure key is defined more than once in
        the mapping template.
    """
    metadata: dict[str, MeasureMeta] = {}

    for row in template.rows:
        key = row.canonical_measure.strip()
        if not key:
            continue  # row does not define a canonical measure

        # Avoid accidental duplicates in the mapping
        if key in metadata:
            raise ValueError(
                f"Duplicate canonical measure key '{key}' in mapping template."
            )

        metadata[key] = MeasureMeta(
            key=key,
            label=row.name,
            unit="amount",  # canonical measures are always monetary amounts
            notes=row.notes or "",
            kind="canonical",
        )

    return metadata
