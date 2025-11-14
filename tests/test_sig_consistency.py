import pytest

from smb_finsight.engine import aggregate
from smb_finsight.io import read_accounting_entries
from smb_finsight.mapping import Template


def test_sig_equals_detailed_and_raw():
    """
    Test that the SIG view, the detailed view, and the raw sum of 6*/7* accounts
    all produce the same net result.
    """
    entries = read_accounting_entries(
        "examples/accounting_entries_large_with_description.csv"
    )

    tpl_detailed = Template.from_csv("data/mappings/detailed_income_statement_pcg.csv")
    tpl_sig = Template.from_csv("data/mappings/sig_pcg.csv")

    out_detailed = aggregate(entries, tpl_detailed)
    out_sig = aggregate(entries, tpl_sig)

    # Extract results
    rn_detailed = out_detailed.loc[
        out_detailed["name"] == "RÉSULTAT NET", "amount"
    ].iloc[0]
    rn_sig = out_sig.loc[out_sig["name"] == "Résultat de l'exercice", "amount"].iloc[0]

    # Raw brute result from accounts 6* and 7*
    raw = entries[entries["code"].astype(str).str.startswith(("6", "7"))][
        "amount"
    ].sum()

    assert rn_detailed == pytest.approx(raw, abs=0.01)
    assert rn_sig == pytest.approx(raw, abs=0.01)
