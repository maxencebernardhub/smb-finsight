import pandas as pd

from smb_finsight.accounts import load_list_of_accounts


def test_load_list_of_accounts_from_minimal_csv(tmp_path):
    """
    load_list_of_accounts should read a CSV with columns
    'account_number' and 'name' and return a usable mapping of codes.
    """
    p = tmp_path / "accounts.csv"
    p.write_text(
        "account_number,name\n60,Purchases\n601,Raw materials\n706,Services revenue\n"
    )

    accounts = load_list_of_accounts(str(p))

    # We accept either a dict-like mapping or a DataFrame.
    if isinstance(accounts, dict):
        # Dict mapping: key -> label
        assert "60" in accounts
        assert "601" in accounts
        assert "706" in accounts
        assert accounts["601"] == "Raw materials"
    elif isinstance(accounts, pd.DataFrame):
        # DataFrame style: must contain these columns
        assert "account_number" in accounts.columns or "code" in accounts.columns
        assert "name" in accounts.columns

        # Normalize column name for code
        code_col = "account_number" if "account_number" in accounts.columns else "code"
        codes = set(str(c).strip() for c in accounts[code_col].tolist())
        assert {"60", "601", "706"}.issubset(codes)
    else:
        raise AssertionError(
            f"Unsupported return type from load_list_of_accounts: {type(accounts)}"
        )
