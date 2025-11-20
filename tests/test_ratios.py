from pathlib import Path

import pytest

from smb_finsight.ratios import (
    RatioResult,
    compute_derived_measures,
    compute_ratios,
)

RATIOS_RULES = Path("ratios/ratios_fr_pcg.toml")


@pytest.mark.skipif(not RATIOS_RULES.exists(), reason="ratios_fr_pcg.toml not found")
def test_compute_derived_measures_integration() -> None:
    """
    Integration test for compute_derived_measures with the FR PCG ratios pack.

    We don't check exact values (formulas may evolve), but we verify that:
    - base measures are preserved,
    - some key derived measures are present and numeric.
    """
    base_measures = {
        "revenue": 1000.0,
        "cost_of_goods_sold": -400.0,
        "net_income": 50.0,
        "depreciation_amortization": 30.0,
        "external_charges": -250.0,
        "personnel_expenses": -300.0,
        "total_assets": 800.0,
        "total_equity": 300.0,
        "financial_debt": 150.0,
        "cash_and_equivalents": 50.0,
        "accounts_receivable": 200.0,
        "accounts_payable": 100.0,
        "inventory": 50.0,
        "average_daily_sales": 10.0,
        "average_daily_purchases": 5.0,
        "average_daily_cost_of_goods_sold": 7.0,
        "average_fte": 5.0,
        "net_financial_expenses": 20.0,
        "income_tax_expense": 15.0,
        "interest_expense": 20.0,
        "operating_income": 80.0,
    }

    derived = compute_derived_measures(base_measures, RATIOS_RULES)

    # Base measures must be preserved
    for k, v in base_measures.items():
        assert k in derived
        assert derived[k] == pytest.approx(v)

    # A few key derived measures should be present and numeric
    for key in ("gross_margin", "gross_margin_pct", "caf", "net_margin_pct"):
        assert key in derived
        assert isinstance(derived[key], float)


@pytest.mark.skipif(not RATIOS_RULES.exists(), reason="ratios_fr_pcg.toml not found")
@pytest.mark.parametrize(
    "level, expected_levels",
    [
        ("basic", {"basic"}),
        ("advanced", {"basic", "advanced"}),
        ("full", {"basic", "advanced", "full"}),
    ],
)
def test_compute_ratios_by_level(level: str, expected_levels: set[str]) -> None:
    """
    compute_ratios should return ratios coming from all included levels,
    and each RatioResult.level should reflect its true logical level.
    """
    base_measures = {
        "revenue": 1000.0,
        "cost_of_goods_sold": -400.0,
        "net_income": 50.0,
        "depreciation_amortization": 30.0,
        "external_charges": -250.0,
        "personnel_expenses": -300.0,
        "total_assets": 800.0,
        "total_equity": 300.0,
        "financial_debt": 150.0,
        "cash_and_equivalents": 50.0,
        "accounts_receivable": 200.0,
        "accounts_payable": 100.0,
        "inventory": 50.0,
        "average_daily_sales": 10.0,
        "average_daily_purchases": 5.0,
        "average_daily_cost_of_goods_sold": 7.0,
        "average_fte": 5.0,
        "net_financial_expenses": 20.0,
        "income_tax_expense": 15.0,
        "interest_expense": 20.0,
        "operating_income": 80.0,
    }

    measures = compute_derived_measures(base_measures, RATIOS_RULES)
    ratios = compute_ratios(measures, RATIOS_RULES, level=level)

    assert isinstance(ratios, list)
    assert ratios, f"No ratios returned for level={level}"

    levels = {r.level for r in ratios}
    # On vérifie qu'on obtient exactement les niveaux attendus
    assert levels == expected_levels

    # Sanity check: chaque ratio a un key/label cohérent
    for r in ratios:
        assert isinstance(r, RatioResult)
        assert isinstance(r.key, str)
        assert isinstance(r.label, str)
