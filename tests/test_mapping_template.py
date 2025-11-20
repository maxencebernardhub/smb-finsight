# tests/test_mapping_template.py

from pathlib import Path

import pytest

from smb_finsight.mapping import Template


def _write_simple_mapping(tmp_path: Path) -> Path:
    """
    Create a minimal income-statement style mapping CSV with:
    - row 1: revenue (70*)
    - row 2: purchases (60*)
    - row 3: gross margin = row1 + row2
    """
    csv_path = tmp_path / "simple_mapping.csv"
    csv_path.write_text(
        "display_order,id,name,type,level,accounts_to_include,"
        "accounts_to_exclude,formula,canonical_measure,notes\n"
        "10,1,Revenus,acc,3,70*,,,revenue,\n"
        "20,2,Achat,acc,3,60*,,,cost_of_goods_sold,\n"
        # Ici on remplit bien la colonne 'formula' avec '=1+2'
        "30,3,Marge brute,calc,1,,,=1+2,gross_margin,\n",
        encoding="utf-8",
    )
    return csv_path


def test_template_match_rows_for_code(tmp_path) -> None:
    """match_rows_for_code should match codes based on simple 70*/60* patterns."""
    csv_path = _write_simple_mapping(tmp_path)
    tpl = Template.from_csv(str(csv_path))

    # Revenue row must match 701000
    rev_matches = tpl.match_rows_for_code("701000")
    assert 1 in rev_matches

    # Purchases row must match 602000
    purchases_matches = tpl.match_rows_for_code("602000")
    assert 2 in purchases_matches

    # Code outside 60* and 70* should not match any row
    none_matches = tpl.match_rows_for_code("512000")
    assert none_matches == []


def test_template_calc_formula_basic(tmp_path) -> None:
    """calc_formula should be able to combine row amounts by id."""
    csv_path = _write_simple_mapping(tmp_path)
    tpl = Template.from_csv(str(csv_path))

    # We emulate aggregated row amounts
    amounts = {1: 1000.0, 2: -400.0}

    # Row 3 is the "gross margin" row, whose formula is '=1+2'
    res = tpl.calc_formula(3, amounts)

    assert res == pytest.approx(600.0)
