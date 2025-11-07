import pandas as pd
import pytest

from smb_finsight.engine import aggregate
from smb_finsight.mapping import Template


def amt(out_df, name: str) -> float:
    row = out_df.loc[out_df["name"] == name]
    assert not row.empty, f"Row '{name}' not found"
    return float(row["amount"].iloc[0])


@pytest.mark.parametrize(
    "template",
    [
        "data/mappings/simplified_income_statement_pcg.csv",
        "data/mappings/regular_income_statement_pcg.csv",
    ],
)
def test_amortization_and_subsidies(template):
    tx = pd.DataFrame(
        [
            {"code": "68110", "debit": 1200.0, "credit": 0.0},  # D&A expense (negative)
            {"code": "60600", "debit": 300.0, "credit": 0.0},  # operating expense
            {"code": "75402", "debit": 0.0, "credit": 1500.0},  # revenue
            {
                "code": "74000",
                "debit": 0.0,
                "credit": 100.0,
            },  # subsidy (adds to revenues)
        ]
    )
    tx["amount"] = tx["credit"].fillna(0) - tx["debit"].fillna(0)
    tx = tx[["code", "amount"]]

    tpl = Template.from_csv(template)
    out = aggregate(tx, tpl)

    oper_rev = (
        amt(out, "Total produits d'exploitation")
        if "Total produits d'exploitation" in out["name"].values
        else amt(out, "TOTAL Produits d'exploitation")
    )
    oper_exp = (
        amt(out, "Total charges d'exploitation")
        if "Total charges d'exploitation" in out["name"].values
        else amt(out, "TOTAL Charges d'exploitation")
    )
    oper_res = (
        amt(out, "Résultat d'exploitation")
        if "Résultat d'exploitation" in out["name"].values
        else amt(out, "RÉSULTAT D'EXPLOITATION")
    )

    # Revenue: 1500 + 100 = 1600
    assert round(oper_rev, 2) == 1600.00
    # Expense: -300 - 1200 = -1500
    assert round(oper_exp, 2) == -1500.00
    # Result: 1600 + (-1500) = 100
    assert round(oper_res, 2) == 100.00


@pytest.mark.parametrize(
    "template",
    [
        "data/mappings/simplified_income_statement_pcg.csv",
        "data/mappings/regular_income_statement_pcg.csv",
    ],
)
def test_production_stocked_and_variations(template):
    tx = pd.DataFrame(
        [
            {"code": "70100", "debit": 0.0, "credit": 2000.0},  # Sales
            {"code": "60300", "debit": 0.0, "credit": 150.0},  # Stock variation (+)
            {"code": "71300", "debit": 0.0, "credit": 50.0},  # Production stored (+)
            {"code": "62201", "debit": 500.0, "credit": 0.0},  # Expense
        ]
    )
    tx["amount"] = tx["credit"].fillna(0) - tx["debit"].fillna(0)
    tx = tx[["code", "amount"]]

    tpl = Template.from_csv(template)
    out = aggregate(tx, tpl)

    oper_rev = (
        amt(out, "Total produits d'exploitation")
        if "Total produits d'exploitation" in out["name"].values
        else amt(out, "TOTAL Produits d'exploitation")
    )
    oper_exp = (
        amt(out, "Total charges d'exploitation")
        if "Total charges d'exploitation" in out["name"].values
        else amt(out, "TOTAL Charges d'exploitation")
    )
    oper_res = (
        amt(out, "Résultat d'exploitation")
        if "Résultat d'exploitation" in out["name"].values
        else amt(out, "RÉSULTAT D'EXPLOITATION")
    )

    # Products = 2000 (sales) + 50 (production stored) = 2050
    assert round(oper_rev, 2) == 2050.00
    # Expenses = -500 (expense) + 150 (stock variation on 603* reduces expenses) = -350
    assert round(oper_exp, 2) == -350.00
    # Result = 2050 + (-350) = 1700
    assert round(oper_res, 2) == 1700.00


@pytest.mark.parametrize(
    "template",
    [
        "data/mappings/simplified_income_statement_pcg.csv",
        "data/mappings/regular_income_statement_pcg.csv",
    ],
)
def test_multiple_financial_and_exceptional_entries(template):
    tx = pd.DataFrame(
        [
            {"code": "76000", "debit": 0.0, "credit": 100.0},  # Financial income
            {"code": "76010", "debit": 0.0, "credit": 25.0},  # Financial income
            {"code": "66100", "debit": 5.0, "credit": 0.0},  # Financial expense
            {"code": "66150", "debit": 10.0, "credit": 0.0},  # Financial expense
            {"code": "77100", "debit": 0.0, "credit": 10.0},  # Exceptional income
            {"code": "67200", "debit": 2.0, "credit": 0.0},  # Exceptional expense
            {"code": "67100", "debit": 3.0, "credit": 0.0},  # Exceptional expense
        ]
    )
    tx["amount"] = tx["credit"].fillna(0) - tx["debit"].fillna(0)
    tx = tx[["code", "amount"]]

    tpl = Template.from_csv(template)
    out = aggregate(tx, tpl)

    fin_res = (
        amt(out, "Résultat financier")
        if "Résultat financier" in out["name"].values
        else amt(out, "RÉSULTAT FINANCIER")
    )
    exc_res = (
        amt(out, "Résultat exceptionnel")
        if "Résultat exceptionnel" in out["name"].values
        else amt(out, "RÉSULTAT EXCEPTIONNEL")
    )

    # Financial: (100 + 25) + (-5 - 10) = 110
    assert round(fin_res, 2) == 110.00
    # Exceptional: 10 + (-2 - 3) = 5
    assert round(exc_res, 2) == 5.00
