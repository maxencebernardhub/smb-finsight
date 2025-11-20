from smb_finsight.engine import aggregate
from smb_finsight.io import read_accounting_entries
from smb_finsight.mapping import Template


def test_sig_basic_structure_and_key_lines() -> None:
    """SIG FR PCG should contain the main intermediate balances with numeric values."""
    entries = read_accounting_entries("data/input/accounting_entries.csv")
    tpl_sig = Template.from_csv("mapping/sig_fr_pcg.csv")

    out_sig = aggregate(entries, tpl_sig)

    key_lines = [
        "Marge commerciale",
        "Marge de production",
        "Valeur ajoutée",
        "Excédent brut d'exploitation (EBE)",
        "Résultat de l'exercice",
    ]

    names = set(out_sig["name"])

    for label in key_lines:
        assert label in names, f"Missing SIG line: {label}"
        value = float(out_sig.loc[out_sig["name"] == label, "amount"].iloc[0])
        # Just check that we can convert to float; zero is allowed.
        assert isinstance(value, float)
