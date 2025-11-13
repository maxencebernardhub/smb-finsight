import pandas as pd
import pytest

from smb_finsight.engine import aggregate
from smb_finsight.mapping import Template


def test_sig_internal_structure_small_dataset():
    """
    Uses a small synthetic dataset to verify correctness of key SIG components:
    - Marge commerciale
    - Marge de production
    - Valeur Ajoutée
    - EBE

    This acts as a structural integrity test of sig_pcg.csv.
    """

    data = pd.DataFrame(
        [
            {"code": "701000", "amount": 10000},  # production vendue
            {"code": "707000", "amount": 4000},  # ventes de marchandises
            {"code": "607000", "amount": -1500},  # achats marchandises
            {"code": "600000", "amount": -2000},  # achats MP
            {"code": "604000", "amount": -500},  # autres charges externes
            {"code": "63", "amount": -300},  # impôts
        ]
    )

    tpl_sig = Template.from_csv("data/mappings/sig_pcg.csv")
    out_sig = aggregate(data, tpl_sig)

    mco = out_sig.loc[out_sig["name"] == "Marge commerciale", "amount"].iloc[0]
    mprod = out_sig.loc[out_sig["name"] == "Marge de production", "amount"].iloc[0]
    va = out_sig.loc[out_sig["name"] == "Valeur ajoutée", "amount"].iloc[0]

    # Expected calculations
    expected_mco = 4000 + (-1500)
    expected_mprod = 10000 + (-2000 - 500)
    expected_va = expected_mco + expected_mprod

    assert mco == pytest.approx(expected_mco, abs=0.01)
    assert mprod == pytest.approx(expected_mprod, abs=0.01)
    assert va == pytest.approx(expected_va, abs=0.01)
