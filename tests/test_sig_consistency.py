import pytest

from smb_finsight.engine import aggregate
from smb_finsight.io import read_accounting_entries
from smb_finsight.mapping import Template


def test_net_result_consistency_between_IS_SIG_and_raw_sum() -> None:
    """
    Check that:
    - raw result from classes 6 and 7,
    - 'RÉSULTAT NET' from income statement,
    - 'Résultat de l'exercice' from SIG,
    are all approximately equal.
    """
    entries = read_accounting_entries("data/input/accounting_entries.csv")

    # Raw result based on PCG sign convention (classes 7: products, 6: charges)
    df = entries.copy()
    df["class"] = df["code"].astype(str).str[0]

    raw_result = df.loc[df["class"].isin(["6", "7"]), "amount"].sum()

    # Income statement FR PCG
    tpl_is = Template.from_csv("mapping/income_statement_fr_pcg.csv")
    out_is = aggregate(entries, tpl_is)

    rn_is = out_is.loc[out_is["name"] == "RÉSULTAT NET", "amount"].iloc[0]

    # SIG FR PCG
    tpl_sig = Template.from_csv("mapping/sig_fr_pcg.csv")
    out_sig = aggregate(entries, tpl_sig)
    rn_sig = out_sig.loc[out_sig["name"] == "Résultat de l'exercice", "amount"].iloc[0]

    assert rn_is == pytest.approx(raw_result, rel=1e-6, abs=1e-6)
    assert rn_sig == pytest.approx(raw_result, rel=1e-6, abs=1e-6)
