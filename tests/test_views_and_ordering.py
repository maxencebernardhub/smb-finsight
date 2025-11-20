import pandas as pd
import pytest

from smb_finsight.accounts import load_list_of_accounts
from smb_finsight.engine import aggregate
from smb_finsight.io import read_accounting_entries
from smb_finsight.mapping import Template
from smb_finsight.views import apply_view_level_filter, build_complete_view


def _is_step10(seq) -> bool:
    return all(b - a == 10 for a, b in zip(seq, seq[1:]))


@pytest.fixture(scope="module")
def income_statement_template() -> Template:
    return Template.from_csv("mapping/income_statement_fr_pcg.csv")


@pytest.fixture(scope="module")
def accounting_entries() -> pd.DataFrame:
    return read_accounting_entries("data/input/accounting_entries.csv")


@pytest.fixture(scope="module")
def accounts_df() -> pd.DataFrame:
    return load_list_of_accounts("data/reference/fr_pcg.csv")


@pytest.fixture(scope="module")
def base_aggregated(income_statement_template, accounting_entries) -> pd.DataFrame:
    return aggregate(accounting_entries, income_statement_template)


def test_apply_view_level_filter_levels_and_order(base_aggregated) -> None:
    simplified = apply_view_level_filter(base_aggregated, "simplified")
    regular = apply_view_level_filter(base_aggregated, "regular")
    detailed = apply_view_level_filter(base_aggregated, "detailed")

    # display_order must be strictly increasing by steps of 10
    for df in (simplified, regular, detailed):
        assert _is_step10(df["display_order"].tolist())

    # Level filtering
    assert simplified["level"].max() <= 1
    assert regular["level"].max() <= 2
    # Detailed keeps all template rows (including level 3)
    assert detailed["level"].max() >= 3


def test_build_complete_view_inserts_level4_children(
    base_aggregated, accounting_entries, income_statement_template, accounts_df
) -> None:
    # Build a name_by_code mapping from the chart of accounts
    code_col = "code"
    if code_col not in accounts_df.columns:
        # Fallback if load_list_of_accounts uses a different column name
        for cand in ("account_number", "account", "num_compte"):
            if cand in accounts_df.columns:
                code_col = cand
                break

    name_col = "name"
    if name_col not in accounts_df.columns:
        for cand in ("label", "description"):
            if cand in accounts_df.columns:
                name_col = cand
                break

    name_by_code = {
        str(row[code_col]).strip(): str(row[name_col]).strip()
        for _, row in accounts_df.iterrows()
    }

    complete = build_complete_view(
        base_aggregated,
        accounting_entries,
        income_statement_template,
        name_by_code,
    )

    # Always ordered by display_order in steps of 10
    assert _is_step10(complete["display_order"].tolist())

    # Find parent "Ventes de marchandises" (level 3)
    parent_idx = complete.index[complete["name"] == "Ventes de marchandises"]
    assert len(parent_idx) == 1, "Parent 'Ventes de marchandises' not found"
    pi = int(parent_idx[0])

    # Its first child must be right after, level + 1, and start with the account code
    assert complete.iloc[pi + 1]["level"] == complete.iloc[pi]["level"] + 1
    assert str(complete.iloc[pi + 1]["name"]).startswith("707000")

    # The next parent (e.g., 'Prestations de services') must come after the child
    assert (
        complete.iloc[pi + 2]["display_order"]
        == complete.iloc[pi + 1]["display_order"] + 10
    )
