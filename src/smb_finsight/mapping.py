# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

from dataclasses import dataclass
from typing import Optional

import pandas as pd


@dataclass
class RowDef:
    display_order: int
    id: int
    name: str
    type: str  # 'acc' or 'calc'
    level: int
    include: str
    exclude: str
    formula: str


def _to_patterns(s: Optional[str]) -> list[str]:
    if s is None or str(s).strip() == "":
        return []
    return [p.strip() for p in str(s).split(";") if p.strip()]


def _match(code: str, patterns: list[str]) -> bool:
    for p in patterns:
        if p.endswith("*"):
            if code.startswith(p[:-1]):
                return True
        else:
            if code == p:
                return True
    return False


class Template:
    def __init__(self, df: pd.DataFrame):
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
                )
            )
        self._by_id = {r.id: r for r in self.rows}

    @staticmethod
    def from_csv(path: str) -> "Template":
        df = pd.read_csv(path)
        # normalize columns
        df.columns = [c.strip() for c in df.columns]
        df = df.fillna("")
        return Template(df)

    def match_rows_for_code(self, code: str) -> list[int]:
        ids = []
        for r in self.rows:
            if r.type != "acc":
                continue
            inc = _to_patterns(r.include)
            exc = _to_patterns(r.exclude)
            if inc and _match(code, inc) and not (exc and _match(code, exc)):
                ids.append(r.id)
        return ids

    def calc_formula(self, row_id: int, values_by_id: dict[int, float]) -> float:
        row = self._by_id[row_id]
        f = row.formula.strip()
        if not f.startswith("="):
            return 0.0
        expr = f[1:].strip()

        # support =A-B, =SUM(1,2,3), =SUM(1,2,3)-10, etc.
        def repl_token(tok: str) -> str:
            tok = tok.strip()
            if tok.isdigit():
                return str(values_by_id.get(int(tok), 0.0))
            return tok

        # simple replacement for tokens inside SUM and arithmetic ops
        import re

        expr = re.sub(
            r"SUM\(([^\)]*)\)",
            lambda m: str(
                sum(
                    float(values_by_id.get(int(t.strip()), 0.0))
                    for t in m.group(1).split(",")
                    if t.strip()
                )
            ),
            expr,
        )
        expr = re.sub(r"\b(\d+)\b", lambda m: repl_token(m.group(1)), expr)

        import re

        # Whitelist: digits, dot, operators, parentheses, comma, whitespace
        if re.search(r"[^0-9\.\+\-\*\/\(\),\s]", expr):
            raise ValueError(f"Invalid characters in formula: {row.formula}")

        return float(eval(expr, {}, {}))
