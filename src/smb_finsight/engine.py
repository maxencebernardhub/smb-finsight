# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

import pandas as pd

from .mapping import Template


def aggregate(accounting_entries: pd.DataFrame, template: Template) -> pd.DataFrame:
    # sum amounts by template row id
    amounts: dict[int, float] = {r.id: 0.0 for r in template.rows}
    # classify each transaction into 0..N rows
    for _, t in accounting_entries.iterrows():
        code = str(t["code"])
        amt = float(t["amount"])
        row_ids = template.match_rows_for_code(code)
        for rid in row_ids:
            amounts[rid] += amt

    # compute calc rows
    for r in template.rows:
        if r.type == "calc":
            amounts[r.id] = template.calc_formula(r.id, amounts)

    # make output
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
