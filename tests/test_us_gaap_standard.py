from pathlib import Path

import pandas as pd
import pytest

from smb_finsight.engine import aggregate, build_canonical_measures
from smb_finsight.io import read_accounting_entries
from smb_finsight.mapping import Template
from smb_finsight.ratios import compute_derived_measures, compute_ratios

# The tests assume the default file structure used for the US GAAP standard:
# - mapping  : mapping/income_statement_us_gaap.csv
# - ratios   : ratios/ratios_us_gaap.toml
# - entries  : data/input/accounting_entries_us_gaap.csv
#
# If your project is organized differently, adjust the file paths below.
BASE_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def us_gaap_paths() -> dict[str, Path]:
    """Return all relevant file paths for the US GAAP standard."""
    return {
        "entries": BASE_DIR / "data" / "input" / "accounting_entries_us_gaap.csv",
        "mapping": BASE_DIR / "mapping" / "income_statement_us_gaap.csv",
        "ratios": BASE_DIR / "ratios" / "ratios_us_gaap.toml",
    }


@pytest.fixture(scope="module")
def us_gaap_template(us_gaap_paths: dict[str, Path]) -> Template:
    """Load the US GAAP mapping template."""
    return Template.from_csv(str(us_gaap_paths["mapping"]))


@pytest.fixture(scope="module")
def us_gaap_entries(us_gaap_paths: dict[str, Path]) -> pd.DataFrame:
    """Load the accounting entries for US GAAP."""
    return read_accounting_entries(str(us_gaap_paths["entries"]))


@pytest.fixture(scope="module")
def us_gaap_statement(
    us_gaap_entries: pd.DataFrame,
    us_gaap_template: Template,
) -> pd.DataFrame:
    """Aggregate entries into an income-statement-shaped dataframe (US GAAP)."""
    return aggregate(us_gaap_entries, us_gaap_template)


@pytest.fixture(scope="module")
def us_gaap_measures(
    us_gaap_statement: pd.DataFrame,
    us_gaap_template: Template,
) -> dict[str, float]:
    """Compute canonical measures from the aggregated US GAAP statement."""
    return build_canonical_measures(us_gaap_statement, us_gaap_template)


# ---------------------------------------------------------------------------
# 1) Verify the presence of canonical measures in the US GAAP mapping
# ---------------------------------------------------------------------------


def test_us_gaap_canonical_measures_present(us_gaap_template: Template) -> None:
    """Ensure that key canonical measures are defined in the US GAAP template."""
    canonical = us_gaap_template.canonical_rows()

    expected_keys = {
        "revenue",
        "cost_of_goods_sold",
        "gross_margin",
        "total_operating_expenses",
        "operating_income",
        "financial_result",
        "income_tax_expense",
        "net_income",
    }

    for key in expected_keys:
        assert key in canonical, f"Missing canonical measure: {key!r}"

    # Basic sanity check on naming consistency
    assert canonical["net_income"].name == "Net income"


# ---------------------------------------------------------------------------
# 2) Validate key canonical measure values from accounting_entries_us_gaap.csv
# ---------------------------------------------------------------------------


def test_us_gaap_canonical_measures_values(us_gaap_measures: dict[str, float]) -> None:
    """
    Validate key aggregated values for the US GAAP dataset.
    If accounting_entries_us_gaap.csv changes, these expected values must be updated.
    """
    m = us_gaap_measures

    # At this stage, the US GAAP dataset is economically identical to CA ASPE,
    # so the values match the CA ASPE canonical measures.
    assert pytest.approx(m["revenue"], rel=1e-6, abs=0.01) == 170_618.55
    assert pytest.approx(m["cost_of_goods_sold"], rel=1e-6, abs=0.01) == 0.0
    assert pytest.approx(m["gross_margin"], rel=1e-6, abs=0.01) == 170_618.55
    assert (
        pytest.approx(m["total_operating_expenses"], rel=1e-6, abs=0.01) == -357_675.81
    )
    assert pytest.approx(m["operating_income"], rel=1e-6, abs=0.01) == -187_057.26
    assert pytest.approx(m["net_income"], rel=1e-6, abs=0.01) == -187_057.26


# ---------------------------------------------------------------------------
# 3) Validate basic ratio computations for US GAAP
# ---------------------------------------------------------------------------


def test_us_gaap_basic_ratios(
    us_gaap_measures: dict[str, float],
    us_gaap_paths: dict[str, Path],
) -> None:
    """Validate gross, operating and net margin computations for US GAAP."""
    rules_file = us_gaap_paths["ratios"]

    # 1) Compute derived measures
    derived = compute_derived_measures(us_gaap_measures, rules_file)

    # 2) Compute "basic" ratio set (includes gross, operating, net margins)
    basic_ratios = compute_ratios(derived, rules_file, level="basic")
    ratio_by_key = {r.key: r for r in basic_ratios}

    # Ensure required ratios exist
    assert "gross_margin_pct" in ratio_by_key
    assert "operating_margin_pct" in ratio_by_key
    assert "net_margin_pct" in ratio_by_key

    # Validate computed values (rounded)
    assert (
        pytest.approx(ratio_by_key["gross_margin_pct"].value, rel=1e-6, abs=0.01)
        == 100.0
    )
    assert (
        pytest.approx(ratio_by_key["operating_margin_pct"].value, rel=1e-6, abs=0.01)
        == -109.6348
    )
    assert (
        pytest.approx(ratio_by_key["net_margin_pct"].value, rel=1e-6, abs=0.01)
        == -109.6348
    )

    # Label consistency checks for US GAAP
    assert ratio_by_key["gross_margin_pct"].label == "Gross profit margin (%)"
    assert ratio_by_key["operating_margin_pct"].label == "Operating profit margin (%)"
    assert ratio_by_key["net_margin_pct"].label == "Net income margin (%)"
