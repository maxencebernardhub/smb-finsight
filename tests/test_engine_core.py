import pandas as pd
import pytest

from smb_finsight.io import read_accounting_entries


def test_io_sign_normalization_debit_credit(tmp_path):
    """read_accounting_entries should compute amount = credit - debit
    with dates/descriptions."""
    p = tmp_path / "ae.csv"
    p.write_text(
        "date,code,description,debit,credit\n"
        "2025-01-01,62201,Postage fees,533.25,0\n"  # expense → amount = -533.25
        "2025-01-02,75402,Ancillary income,0,844.65\n"  # revenue → amount = +844.65
    )

    df = read_accounting_entries(str(p))

    # colonnes normalisées
    assert list(df.columns) == ["date", "code", "description", "amount"]

    # types
    assert pd.api.types.is_datetime64_any_dtype(df["date"])
    assert df["amount"].dtype.kind == "f"

    # signe des montants
    assert df.loc[0, "amount"] == pytest.approx(-533.25)
    assert df.loc[1, "amount"] == pytest.approx(844.65)


def test_io_sign_normalization_amount_column(tmp_path):
    """read_accounting_entries should accept a pre-computed signed 'amount' column."""
    p = tmp_path / "ae_amount.csv"
    p.write_text(
        "date,code,description,amount\n"
        "2025-02-01,706000,Consulting services,+1000.00\n"
        "2025-02-02,622000,Rent,-500.00\n"
    )

    df = read_accounting_entries(str(p))

    assert list(df.columns) == ["date", "code", "description", "amount"]
    assert df["amount"].tolist() == [pytest.approx(1000.0), pytest.approx(-500.0)]
