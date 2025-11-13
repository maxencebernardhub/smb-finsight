import pandas as pd

from smb_finsight.engine import aggregate
from smb_finsight.io import read_accounting_entries
from smb_finsight.mapping import Template


def test_io_sign_normalization_debit_credit(tmp_path):
    """read_accounting_entries should compute amount = credit - debit."""
    p = tmp_path / "ae.csv"
    p.write_text(
        "code,debit,credit\n"
        "62201,533.25,0\n"  # expense → amount = -533.25
        "75402,0,844.65\n"  # revenue → amount = +844.65
    )
    df = read_accounting_entries(str(p))
    assert list(df.columns) == ["code", "amount"]

    # Cast code to string to be robust against numeric parsing
    codes = df["code"].astype(str)

    mask_charge = codes == "62201"
    mask_prod = codes == "75402"

    # Sanity checks to avoid empty selections
    assert mask_charge.any()
    assert mask_prod.any()

    row_charge = float(df.loc[mask_charge, "amount"].iloc[0])
    row_prod = float(df.loc[mask_prod, "amount"].iloc[0])

    assert row_charge == -533.25
    assert row_prod == 844.65


def test_engine_aggregate_with_detailed_template():
    """Aggregate should populate a structured DataFrame using the detailed mapping."""
    tx = pd.DataFrame(
        [
            {"code": "706000", "amount": 1000.0},  # services (revenue)
            {"code": "781000", "amount": 500.0},  # operating write-backs (revenue)
        ]
    )
    tpl = Template.from_csv("data/mappings/detailed_income_statement_pcg.csv")
    out = aggregate(tx, tpl)

    # Expected columns present
    for col in ["level", "display_order", "id", "name", "type", "amount"]:
        assert col in out.columns

    # A simple sanity check on amounts (exact totals depend on mapping structure)
    assert out["amount"].max() >= 1500.0
