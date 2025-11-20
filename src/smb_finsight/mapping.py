# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
Mapping utilities for SMB FinSight.

This module defines the structures and logic used to interpret mapping
CSV files that describe how raw accounting entries should be aggregated
into higher-level financial statements (Income Statement, SIG, etc.).

A mapping file defines:
- the list of rows to display (RowDef),
- which accounts to include/exclude in each row,
- how calculated rows depend on other rows,
- and optionally which rows represent canonical financial measures
  (e.g., "revenue", "gross_margin", "ebe", "net_income").

Canonical measures are used later by the engine to build a unified set
of financial metrics that feed the ratio/KPI computation engine.

This module exposes:
- RowDef:     Representation of a single mapping row.
- Template:   Container for all rows of a mapping file, with helpers
              for row lookup and canonical measure extraction.
"""

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class RowDef:
    """Definition of a single mapping row (one output line).

    Attributes:
        display_order: Ordering hint used when rendering the statement.
        id: Unique integer identifier for the row (used in formulas).
        name: Human-readable label (e.g. 'Operating income').
        type: Row type:
            - 'acc'  → aggregation of accounts (sum of amounts),
            - 'calc' → formula based on other row IDs.
        level: Hierarchical level (0 = top, 1..N = nested).
        include: Semicolon-separated patterns of accounts to include.
        exclude: Semicolon-separated patterns of accounts to exclude.
        formula: Formula string for 'calc' rows (e.g. '=1+2', '=SUM(4;5)').
        canonical_measure: Optional canonical measure name used to feed
            derived financial metrics and ratios (e.g. 'revenue', 'ebe').
    """

    display_order: int
    id: int
    name: str
    type: str  # 'acc' or 'calc'
    level: int
    include: str
    exclude: str
    formula: str
    canonical_measure: str = ""


def _to_patterns(s: Optional[str]) -> list[str]:
    """Convert a semicolon-separated pattern string into a list.

    Examples:
        "70*;71*" → ["70*", "71*"]
        None or "" → []

    Args:
        s: Raw pattern string from the CSV (may be None or empty).

    Returns:
        A list of stripped pattern strings.
    """
    if s is None or str(s).strip() == "":
        return []
    return [p.strip() for p in str(s).split(";") if p.strip()]


def _match(code: str, patterns: list[str]) -> bool:
    """Return True if an account code matches at least one pattern.

    Rules:
        - '70*' matches any account starting with '70' (e.g. '701', '709').
        - '62201' matches only the exact code '62201'.

    Args:
        code: Account code as a string.
        patterns: List of include/exclude patterns.

    Returns:
        True if the code matches any pattern, False otherwise.
    """
    for p in patterns:
        if p.endswith("*"):
            if code.startswith(p[:-1]):
                return True
        else:
            if code == p:
                return True
    return False


class Template:
    """In-memory representation of a mapping template.

    A Template is constructed from a CSV that describes each output row.
    It is responsible for:
      - storing RowDef entries,
      - finding which rows an account code contributes to,
      - computing formula rows based on previously aggregated values.
    """

    def __init__(self, df: pd.DataFrame):
        """Build a Template from a DataFrame.

        The DataFrame is typically loaded from a CSV and must contain at least
        the columns required to build RowDef instances:
        display_order, id, name, type, level, accounts_to_include,
        accounts_to_exclude, formula.

        Optionally, it may also contain a 'canonical_measure' column used to
        tag specific rows as canonical financial measures (e.g. 'revenue',
        'gross_margin', 'ebe', 'net_income').
        """
        self.rows: list[RowDef] = []
        for _, r in df.iterrows():
            self.rows.append(
                RowDef(
                    display_order=int(r["display_order"]),
                    id=int(r["id"]),
                    name=str(r["name"]),
                    type=str(r["type"]),
                    level=int(r["level"]),
                    include=str(
                        r.get("accounts_to_include", "")
                        if pd.notna(r.get("accounts_to_include", ""))
                        else ""
                    ),
                    exclude=str(
                        r.get("accounts_to_exclude", "")
                        if pd.notna(r.get("accounts_to_exclude", ""))
                        else ""
                    ),
                    formula=str(
                        r.get("formula", "") if pd.notna(r.get("formula", "")) else ""
                    ),
                    canonical_measure=str(
                        r.get("canonical_measure", "")
                        if pd.notna(r.get("canonical_measure", ""))
                        else ""
                    ),
                )
            )
        # Fast lookup by row id, used during formula evaluation.
        self._by_id = {r.id: r for r in self.rows}

    def canonical_rows(self) -> dict[str, RowDef]:
        """Return a mapping from canonical_measure name to RowDef.

        Only rows with a non-empty canonical_measure are included.
        """
        return {r.canonical_measure: r for r in self.rows if r.canonical_measure}

    @staticmethod
    def from_csv(path: str) -> "Template":
        """Load a Template directly from a CSV file.

        Args:
            path: Path to the mapping CSV file.

        Returns:
            A Template instance populated with RowDef rows from the file.
        """
        df = pd.read_csv(path)
        # Normalize column names: strip surrounding spaces.
        df.columns = [c.strip() for c in df.columns]
        # Replace NaNs with empty strings to simplify downstream handling.
        df = df.fillna("")
        return Template(df)

    def match_rows_for_code(self, code: str) -> list[int]:
        """Return the list of row IDs that the given account code maps to.

        A row is considered a match if:
          - the code matches at least one pattern in its `include` list, and
          - the code does **not** match any pattern in its `exclude` list.

        Only rows of type 'acc' are considered; 'calc' rows are computed
        afterwards using formulas.

        Args:
            code: Account code (e.g. '62201', '707000').

        Returns:
            List of row IDs (integers). May be empty if no row matches.
        """
        ids: list[int] = []
        for r in self.rows:
            if r.type != "acc":
                continue
            inc = _to_patterns(r.include)
            exc = _to_patterns(r.exclude)
            if inc and _match(code, inc) and not (exc and _match(code, exc)):
                ids.append(r.id)
        return ids

    def calc_formula(self, row_id: int, values_by_id: dict[int, float]) -> float:
        """Evaluate the formula associated with a 'calc' row.

        The formula can:
          - reference other rows by ID (e.g. '=1+2'),
          - use SUM(...) (e.g. '=SUM(1;2;3)'),
          - combine these with basic arithmetic operators (+, -, *, /).

        Process:
            1. Strip leading '='.
            2. Expand SUM(...) into numeric sums.
            3. Replace numeric tokens by values from `values_by_id`.
            4. Validate the expression (whitelist allowed characters).
            5. Evaluate via `eval` in a restricted environment.

        Args:
            row_id: ID of the row whose formula should be evaluated.
            values_by_id: Mapping {row_id: amount} for already computed rows.

        Returns:
            The computed numeric value for the row. If the row formula does not
            start with '=', the function returns 0.0.
        """
        row = self._by_id[row_id]
        f = row.formula.strip()
        if not f.startswith("="):
            return 0.0
        expr = f[1:].strip()

        # Support expressions such as:
        #   =A-B
        #   =SUM(1;2;3)
        #   =SUM(1;2;3)-10
        def repl_token(token: str) -> str:
            """Replace a token (potential row id) by its numeric value.

            - 'SUM' is preserved as a keyword.
            - Non-digit tokens are returned unchanged (operators, etc.).
            - Digit tokens are interpreted as row IDs and replaced by
              values from `values_by_id` (default 0.0 if missing).
            """
            if token.upper() == "SUM":
                return "SUM"
            if not token.isdigit():
                return token
            rid = int(token)
            return str(values_by_id.get(rid, 0.0))

        import re

        # 1) First : replace IDs (1,2,3,...) by their numerical values.
        expr = re.sub(r"\b(\d+)\b", lambda m: repl_token(m.group(1)), expr)

        # 2) Then : develop SUM(...) by calculating the sum of its arguments,
        # already replaced.
        expr = re.sub(
            r"SUM\(([^\)]*)\)",
            lambda m: str(
                sum(float(t.strip()) for t in m.group(1).split(";") if t.strip())
            ),
            expr,
        )

        # Whitelist: digits, dot, operators, parentheses, comma, whitespace.
        # Any other character is considered unsafe/invalid.
        if re.search(r"[^0-9\.\+\-\*\/\(\),\s]", expr):
            raise ValueError(f"Invalid characters in formula: {row.formula}")

        return float(eval(expr, {}, {}))
