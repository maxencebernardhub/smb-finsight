import pandas as pd
import pytest

from smb_finsight.io import read_accounting_entries


def test_io_sign_normalization_debit_credit(tmp_path) -> None:
    """When debit/credit columns are present, amount should be credit - debit."""
    csv_path = tmp_path / "entries_dc.csv"
    csv_path.write_text(
        "date,code,description,debit,credit\n"
        "2025-01-01,607000,Purchase A,533.25,0.00\n"
        "2025-01-02,707000,Sale B,0.00,844.65\n",
        encoding="utf-8",
    )

    df = read_accounting_entries(str(csv_path))

    assert list(df.columns) == ["date", "code", "description", "amount"]
    assert pd.api.types.is_datetime64_any_dtype(df["date"])

    # Expense: amount should be negative
    assert df.loc[0, "amount"] == pytest.approx(-533.25)
    # Revenue: amount should be positive
    assert df.loc[1, "amount"] == pytest.approx(844.65)


def test_io_sign_normalization_amount_column(tmp_path) -> None:
    """When only 'amount' is present, it should be preserved as-is."""
    csv_path = tmp_path / "entries_amount.csv"
    csv_path.write_text(
        "date,code,description,amount\n"
        "2025-01-01,607000,Purchase A,-100.0\n"
        "2025-01-02,707000,Sale B,250.0\n",
        encoding="utf-8",
    )

    df = read_accounting_entries(str(csv_path))

    assert list(df.columns) == ["date", "code", "description", "amount"]
    assert df.loc[0, "amount"] == pytest.approx(-100.0)
    assert df.loc[1, "amount"] == pytest.approx(250.0)
