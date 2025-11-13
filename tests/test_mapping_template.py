import pytest

from smb_finsight.mapping import Template


def _write_simple_mapping(tmp_path):
    """Create a small temporary mapping CSV for testing Template behavior."""
    p = tmp_path / "mapping.csv"
    lines = []

    # Header
    lines.append(
        "display_order,id,name,type,level,accounts_to_include,accounts_to_exclude,formula,notes\n"
    )

    # Row 1: Revenues (accounts 70*)
    lines.append(
        ",".join(
            [
                "10",  # display_order
                "1",  # id
                "Revenues",  # name
                "acc",  # type
                "1",  # level
                "70*",  # accounts_to_include
                "",  # accounts_to_exclude
                "",  # formula
                "",  # notes
            ]
        )
        + "\n"
    )

    # Row 2: Expenses (accounts 60*)
    lines.append(
        ",".join(
            [
                "20",
                "2",
                "Expenses",
                "acc",
                "1",
                "60*",
                "",
                "",
                "",
            ]
        )
        + "\n"
    )

    # Row 3: Result simple = 1 + 2
    lines.append(
        ",".join(
            [
                "30",
                "3",
                "Result simple",
                "calc",
                "0",
                "",  # accounts_to_include
                "",  # accounts_to_exclude
                "=1+2",  # formula
                "",  # notes
            ]
        )
        + "\n"
    )

    # Row 4: Result with multiple ids = 1 + 2 + 3
    # (no commas inside the formula to keep CSV parsing simple)
    lines.append(
        ",".join(
            [
                "40",
                "4",
                "Result with multiple ids",
                "calc",
                "0",
                "",
                "",
                "=SUM(1;2;3)",
                "",
            ]
        )
        + "\n"
    )

    p.write_text("".join(lines))
    return p


def test_template_from_csv_and_match_rows_for_code(tmp_path):
    """Template.from_csv should load rows and match accounts using PCG-like patterns."""
    mapping_path = _write_simple_mapping(tmp_path)
    tpl = Template.from_csv(str(mapping_path))

    # We expect 4 rows with the correct ids
    ids = sorted(r.id for r in tpl.rows)
    assert ids == [1, 2, 3, 4]

    # Codes starting with 70 should match Revenues (id=1)
    assert 1 in tpl.match_rows_for_code("700000")
    assert 1 in tpl.match_rows_for_code("701")
    assert 1 in tpl.match_rows_for_code("70999")

    # Codes starting with 60 should match Expenses (id=2)
    assert 2 in tpl.match_rows_for_code("600000")
    assert 2 in tpl.match_rows_for_code("601")
    assert 2 in tpl.match_rows_for_code("60999")

    # A code that does not match 60* or 70* should not match any row
    assert tpl.match_rows_for_code("500000") == []


def test_calc_formula_simple_addition(tmp_path):
    """Template.calc_formula should evaluate basic formulas like =1+2."""
    mapping_path = _write_simple_mapping(tmp_path)
    tpl = Template.from_csv(str(mapping_path))

    # Simulate aggregated values by row id
    values = {1: 100.0, 2: -40.0, 3: 0.0, 4: 0.0}
    result = tpl.calc_formula(3, values)  # =1+2
    assert pytest.approx(result, rel=1e-6) == 60.0


def test_calc_formula_with_sum_function(tmp_path):
    """Template.calc_formula should handle formulas with multiple row ids."""
    mapping_path = _write_simple_mapping(tmp_path)
    tpl = Template.from_csv(str(mapping_path))

    # Values for ids 1, 2, 3
    values = {1: 10.0, 2: 20.0, 3: 30.0, 4: 0.0}
    result = tpl.calc_formula(4, values)  # formula: =SUM(1;2;3)
    assert pytest.approx(result, rel=1e-6) == 60.0


def test_calc_formula_basic_arithmetic(tmp_path):
    """Template.calc_formula should evaluate simple arithmetic like =1+2-3."""

    # Create a simple mapping with 4 rows:
    # 1, 2, 3 = plain values
    # 4       = calc row with formula =1+2-3
    mapping_csv = (
        "display_order,id,name,type,level,accounts_to_include,accounts_to_exclude,formula\n"
        "10,1,Row1,acc,2,,,\n"
        "20,2,Row2,acc,2,,,\n"
        "30,3,Row3,acc,2,,,\n"
        "40,4,Row4,calc,2,,,=1+2-3\n"
    )

    p = tmp_path / "mapping_basic_arith.csv"
    p.write_text(mapping_csv)

    tpl = Template.from_csv(str(p))

    # Provide values for rows 1, 2, 3
    values = {1: 10.0, 2: 20.0, 3: 30.0}

    # Expected: 10 + 20 - 30 = 0
    result = tpl.calc_formula(4, values)

    assert pytest.approx(result, rel=1e-6) == 0.0
