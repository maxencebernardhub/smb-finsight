import pandas as pd
import pytest

from smb_finsight.engine import aggregate
from smb_finsight.mapping import Template


# Helper: get amount by row id
def amt(out_df: pd.DataFrame, row_id: int) -> float:
    row = out_df.loc[out_df["id"] == row_id]
    assert not row.empty, f"Row id {row_id} not found in output"
    return float(row["amount"].iloc[0])


# Mapping-specific IDs for totals/results
IDMAP = {
    "simplified": {
        "oper_rev": 1,  # Total produits d'exploitation
        "oper_exp": 2,  # Total charges d'exploitation
        "oper_res": 3,  # Résultat d'exploitation
        "fin_rev": 4,  # Produits financiers
        "fin_exp": 5,  # Charges financières
        "fin_res": 6,  # Résultat financier
        "exc_rev": 7,  # Produits exceptionnels
        "exc_exp": 8,  # Charges exceptionnelles
        "exc_res": 9,  # Résultat exceptionnel
        "tax": 10,  # Impôt sur les bénéfices
        "net": 11,  # Résultat net
    },
    "regular": {
        "oper_rev": 7,  # TOTAL Produits d'exploitation
        "oper_exp": 14,  # TOTAL Charges d'exploitation
        "oper_res": 15,  # RÉSULTAT D'EXPLOITATION
        "fin_rev": 16,  # Produits financiers
        "fin_exp": 17,  # Charges financières
        "fin_res": 18,  # RÉSULTAT FINANCIER
        "exc_rev": 19,  # Produits exceptionnels
        "exc_exp": 20,  # Charges exceptionnelles
        "exc_res": 21,  # RÉSULTAT EXCEPTIONNEL
        "tax": 22,  # Impôt sur les bénéfices
        "net": 23,  # RÉSULTAT NET
    },
}


@pytest.mark.parametrize(
    "template, ids",
    [
        ("data/mappings/simplified_income_statement_pcg.csv", IDMAP["simplified"]),
        ("data/mappings/regular_income_statement_pcg.csv", IDMAP["regular"]),
    ],
)
def test_basic_operating_result(template, ids):
    # Using engine convention: amount = credit - debit
    tx = pd.DataFrame(
        [
            {
                "code": "62201",
                "debit": 533.25,
                "credit": 0.0,
            },  # operating expense (negative amount)
            {
                "code": "75402",
                "debit": 0.0,
                "credit": 844.65,
            },  # operating revenue (positive amount)
        ]
    )
    # Normalize to amount, as engine.aggregate expects 'code' and 'amount' columns
    tx["amount"] = tx["credit"].fillna(0) - tx["debit"].fillna(0)
    tx = tx[["code", "amount"]]

    tpl = Template.from_csv(template)
    out = aggregate(tx, tpl)

    assert round(amt(out, ids["oper_rev"]), 2) == 844.65
    assert round(amt(out, ids["oper_exp"]), 2) == -533.25
    assert round(amt(out, ids["oper_res"]), 2) == 311.40
    # no other sections yet
    assert round(amt(out, ids["net"]), 2) == 311.40


@pytest.mark.parametrize(
    "template, ids",
    [
        ("data/mappings/simplified_income_statement_pcg.csv", IDMAP["simplified"]),
        ("data/mappings/regular_income_statement_pcg.csv", IDMAP["regular"]),
    ],
)
def test_revenue_with_rebate_709(template, ids):
    tx = pd.DataFrame(
        [
            {"code": "70100", "debit": 0.0, "credit": 1000.0},  # sale
            {"code": "70900", "debit": 0.0, "credit": 0.0},  # explicit 0 line (control)
            {
                "code": "70910",
                "debit": 50.0,
                "credit": 0.0,
            },  # rebate (debit on 709 => negative revenue amount)
            {"code": "62201", "debit": 400.0, "credit": 0.0},  # expense
        ]
    )
    tx["amount"] = tx["credit"].fillna(0) - tx["debit"].fillna(0)
    tx = tx[["code", "amount"]]

    tpl = Template.from_csv(template)
    out = aggregate(tx, tpl)

    # Revenues should be 1000 - 50 = 950
    assert round(amt(out, ids["oper_rev"]), 2) == 950.00
    # Expenses = -400
    assert round(amt(out, ids["oper_exp"]), 2) == -400.00
    # Operating result = 950 + (-400) = 550
    assert round(amt(out, ids["oper_res"]), 2) == 550.00


@pytest.mark.parametrize(
    "template, ids",
    [
        ("data/mappings/simplified_income_statement_pcg.csv", IDMAP["simplified"]),
        ("data/mappings/regular_income_statement_pcg.csv", IDMAP["regular"]),
    ],
)
def test_expense_credit_avoir_and_product_debit_return(template, ids):
    tx = pd.DataFrame(
        [
            {"code": "62201", "debit": 300.0, "credit": 0.0},  # expense (−300)
            {
                "code": "62201",
                "debit": 0.0,
                "credit": 50.0,
            },  # expense credit (avoir) => +50, reduces total expense magnitude
            {"code": "70700", "debit": 0.0, "credit": 800.0},  # revenue (+800)
            {
                "code": "70700",
                "debit": 30.0,
                "credit": 0.0,
            },  # revenue debit (return/allowance) => −30
        ]
    )
    tx["amount"] = tx["credit"].fillna(0) - tx["debit"].fillna(0)
    tx = tx[["code", "amount"]]

    tpl = Template.from_csv(template)
    out = aggregate(tx, tpl)

    # Revenues = 800 - 30 = 770
    assert round(amt(out, ids["oper_rev"]), 2) == 770.00
    # Expenses = -300 + 50 = -250
    assert round(amt(out, ids["oper_exp"]), 2) == -250.00
    # Operating result = 770 + (-250) = 520
    assert round(amt(out, ids["oper_res"]), 2) == 520.00


@pytest.mark.parametrize(
    "template, ids",
    [
        ("data/mappings/simplified_income_statement_pcg.csv", IDMAP["simplified"]),
        ("data/mappings/regular_income_statement_pcg.csv", IDMAP["regular"]),
    ],
)
def test_financial_and_tax_and_exceptional(template, ids):
    tx = pd.DataFrame(
        [
            {"code": "70700", "debit": 0.0, "credit": 1000.0},  # operating revenue
            {"code": "60600", "debit": 200.0, "credit": 0.0},  # operating expense
            {"code": "76000", "debit": 0.0, "credit": 10.0},  # financial revenue
            {"code": "66000", "debit": 4.0, "credit": 0.0},  # financial expense
            {"code": "77000", "debit": 0.0, "credit": 3.0},  # exceptional revenue
            {"code": "67000", "debit": 1.0, "credit": 0.0},  # exceptional expense
            {"code": "69100", "debit": 50.0, "credit": 0.0},  # income tax (charge)
        ]
    )
    tx["amount"] = tx["credit"].fillna(0) - tx["debit"].fillna(0)
    tx = tx[["code", "amount"]]

    tpl = Template.from_csv(template)
    out = aggregate(tx, tpl)

    # Operating: 1000 + (-200) = 800
    assert round(amt(out, ids["oper_res"]), 2) == 800.00
    # Financial: 10 + (-4) = 6
    assert round(amt(out, ids["fin_res"]), 2) == 6.00
    # Exceptional: 3 + (-1) = 2
    assert round(amt(out, ids["exc_res"]), 2) == 2.00
    # Net: 800 + 6 + 2 + (-50) = 758
    assert round(amt(out, ids["net"]), 2) == 758.00
