import pandas as pd

from smb_finsight.accounts import filter_unknown_accounts, load_list_of_accounts


def test_load_list_of_accounts_from_minimal_csv(tmp_path) -> None:
    """load_list_of_accounts should normalize column names and detect code + name."""
    csv_path = tmp_path / "accounts.csv"
    csv_path.write_text(
        "account_number,name\n60,Purchases\n601,Raw materials\n706,Services revenue\n",
        encoding="utf-8",
    )

    df = load_list_of_accounts(str(csv_path))

    assert isinstance(df, pd.DataFrame)
    # Internally we should have at least 'code' and 'name'
    assert "code" in df.columns
    assert "name" in df.columns

    codes = set(df["code"].astype(str))
    assert {"60", "601", "706"} <= codes


def test_filter_unknown_accounts_with_prefix_matching(tmp_path) -> None:
    """filter_unknown_accounts should keep only entries whose code is
    known (by prefix)."""
    accounts_csv = tmp_path / "accounts.csv"
    accounts_csv.write_text(
        "account_number,name\n60,Purchases\n601,Raw materials\n706,Services revenue\n",
        encoding="utf-8",
    )

    accounts_df = load_list_of_accounts(str(accounts_csv))
    known_codes = set(accounts_df["code"].astype(str))

    entries = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2025-01-01", "2025-01-02", "2025-01-03", "2025-01-04"]
            ),
            "code": ["601", "6011", "706", "9999"],
            "description": ["A", "B", "C", "D"],
            "amount": [10.0, 20.0, 30.0, 40.0],
        }
    )

    filtered = filter_unknown_accounts(entries, known_codes)

    # 601 (exact), 6011 (prefix 601) and 706 are kept; 9999 is dropped
    assert set(filtered["code"]) == {"601", "6011", "706"}
