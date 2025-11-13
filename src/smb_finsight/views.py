# SMB FinSight - Financial Dashboard & Analysis application for SMBs
# Copyright (c) 2025 Maxence Bernard (maxencebernardhub)
# Licensed under the MIT License. See LICENSE file for details.

"""
View utilities for SMB FinSight.

This module contains helpers that transform the aggregated income statement
into different "views" of detail:

- simplified: levels 0–1 (very aggregated)
- regular:    levels 0–2 (standard income statement)
- detailed:   all template levels (0–3)
- complete:   same as detailed, but with account-level lines
              inserted under level-3 'acc' rows.
- sig:        Soldes Intermédiaires de Gestion (SIG) based on a dedicated
              mapping template (e.g. data/mappings/sig_pcg.csv).

The aggregation itself is performed by `engine.aggregate`. This module operates
on the resulting DataFrame and, for the 'complete' view, also uses the mapping
template and the chart of accounts (list of accounts).
"""

from collections import defaultdict

import pandas as pd

from .mapping import Template


def apply_view_level_filter(out: pd.DataFrame, view: str) -> pd.DataFrame:
    """Return a view-specific slice with harmonized display_order and columns.

    - simplified: keep levels <= 1
    - regular:    keep levels <= 2
    - detailed:   keep all rows (no level filter)
    - sig:        keep all rows (no level filter, relies on SIG mapping template)

    Steps:
      1) filter by view
      2) sort by the *template* display_order (ascending)
      3) renumber display_order to 10, 20, 30, ...
      4) reorder columns: display_order, id, level, name, type, amount

    Note:
      This helper is NOT used for the 'complete' view (which inserts level-4
      children). All other views, including 'sig', rely entirely on the
      mapping template and generic filtering logic.
    """
    # 1) Filtering by view
    if view == "simplified":
        df = out[out["level"] <= 1].copy()
    elif view == "regular":
        df = out[out["level"] <= 2].copy()
    else:
        # 'detailed', 'sig', or any other non-simplified/non-regular view:
        # no level-based filtering; rely entirely on the mapping template.
        df = out.copy()

    # 2) Sorting according to the original display_order (from the mapping/template)
    if "display_order" in df.columns:
        df = df.sort_values("display_order", ascending=True, kind="stable")
    df = df.reset_index(drop=True)

    # 3) Renumbering of display_order (respects the current order of the lines)
    df["display_order"] = (df.index + 1) * 10

    # 3) Ordering columns for CSV export
    ordered_cols = ["display_order", "id", "level", "name", "type", "amount"]
    df = df[[c for c in ordered_cols if c in df.columns]]

    return df


def build_complete_view(
    out_base: pd.DataFrame,
    accounting_entries: pd.DataFrame,
    template: Template,
    name_by_code: dict[str, str],
) -> pd.DataFrame:
    """Return a 'complete' view with account-level rows inserted.

    The 'complete' view is defined as:

    - all rows of the 'detailed' view (i.e. all template rows, aggregated),
    - for each level-3 'acc' row, we insert its underlying account codes
      (from accounting entries) as level-4 rows.

    The resulting DataFrame preserves the hierarchical ordering:

      level 0 : top-level aggregates
      level 1 : major sub-aggregates
      level 2 : intermediate aggregates (from the template)
      level 3 : leaf 'acc' rows (from the template)
      level 4 : individual accounts (from accounting entries) grouped
                under their parent level-3 'acc' row.

    All rows share the same columns: display_order, id, level, name, type, amount.
    """

    # 1) Base "detailed" view: all template rows and their amounts.
    base = out_base.copy()

    # Map row id -> amount (already rounded in out_base, but kept as reference).
    amounts_by_id: dict[int, float] = {
        int(row["id"]): float(row["amount"]) for _, row in base.iterrows()
    }

    # 2) Aggregate accounting entries by account code.
    by_code = accounting_entries.groupby("code", as_index=False)["amount"].sum()
    # Keep only non-zero accounts to avoid noisy output.
    by_code = by_code[by_code["amount"] != 0.0].copy()
    by_code["code"] = by_code["code"].astype(str).str.strip()

    # 3) Pre-compute, for each level-3 row_id, the list of accounts
    #    (code, amount) that are mapped to it.
    children_by_row_id: dict[int, list[tuple[str, float]]] = defaultdict(list)

    for _, row in by_code.iterrows():
        code = str(row["code"])
        amt = float(row["amount"])
        # For each account, determine which template rows it contributes to.
        row_ids = template.match_rows_for_code(code)
        for rid in row_ids:
            r = template._by_id[rid]
            # We only expand child accounts under 'acc' rows at level 3.
            if r.type == "acc" and r.level == 3:
                children_by_row_id[rid].append((code, amt))

    # 4) Rebuild the complete view in template order, inserting account-level
    #    rows directly below their parent level-3 rows.
    rows_sorted = sorted(template.rows, key=lambda x: x.display_order)

    rows_out: list[dict[str, object]] = []
    current_do = 0  # last assigned display_order for any printed row

    # Walk template rows in order; assign display_order strictly increasing by 10
    for r in rows_sorted:
        amount = round(amounts_by_id.get(r.id, 0.0), 2)

        # Assign a strictly increasing display_order by steps of 10
        template_do = int(r.display_order)
        line_do = max(template_do, current_do + 10)

        if r.level == 3 and r.type == "acc":
            # Print the parent at line_do
            rows_out.append(
                {
                    "level": r.level,
                    "display_order": line_do,
                    "id": r.id,
                    "name": r.name,
                    "type": r.type,
                    "amount": amount,
                }
            )

            # Children (sorted by account code): parent_do + 10, +20, ...(sorted by
            # account code)
            child_accounts = sorted(
                children_by_row_id.get(r.id, []), key=lambda x: x[0]
            )
            if child_accounts:
                last_child_do = line_do
                for idx, (code, amt) in enumerate(child_accounts, start=1):
                    label = name_by_code.get(code, "")
                    full_name = (f"{code} {label}").strip()
                    child_do = line_do + 10 * idx

                    rows_out.append(
                        {
                            "level": r.level + 1,
                            "display_order": child_do,
                            "id": int(r.id) * 1000 + idx,
                            "name": full_name,
                            "type": "acc",
                            "amount": round(float(amt), 2),
                        }
                    )
                    last_child_do = child_do

                # Next row (whatever its level) will start after the last child
                current_do = last_child_do
            else:
                # No children: next row starts after this parent
                current_do = line_do
        else:
            # Non-level-3 rows: just print with adjusted DO; no children to append
            rows_out.append(
                {
                    "level": r.level,
                    "display_order": line_do,
                    "id": r.id,
                    "name": r.name,
                    "type": r.type,
                    "amount": amount,
                }
            )
            current_do = line_do

    df = pd.DataFrame(rows_out)
    # IMPORTANT : we don't change the order of the rows that the function created.
    # We simppy renumber display_order to 10,20,30... and reorder the columns.
    return _finalize_view(df)


def _renumber_display_order(
    df: pd.DataFrame, start: int = 10, step: int = 10
) -> pd.DataFrame:
    """Reassign display_order to be strictly sequential: start, start+step, ...
    Preserves the current order of the lines (as it appears in df).
    """
    df = df.copy()
    df = df.reset_index(drop=True)
    df["display_order"] = [start + i * step for i in range(len(df))]
    return df


def _reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Reorder the columns for the final CSV export."""
    ordered = ["display_order", "id", "level", "name", "type", "amount"]
    cols = [c for c in ordered if c in df.columns]
    return df[cols]


def _finalize_view(df: pd.DataFrame) -> pd.DataFrame:
    """Sorting (if necessary), sequential renumbering of display_order,
    column order."""
    # We keep the CURRENT order of the lines (df) as the display order,
    # then we renumber display_order 10, 20, 30...
    df = _renumber_display_order(df, start=10, step=10)
    df = _reorder_columns(df)
    return df
