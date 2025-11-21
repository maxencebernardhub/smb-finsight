from pathlib import Path

import pandas as pd
import pytest

from smb_finsight.engine import aggregate, build_canonical_measures
from smb_finsight.io import read_accounting_entries
from smb_finsight.mapping import Template
from smb_finsight.ratios import compute_derived_measures, compute_ratios

# The tests assume the default file structure used for the IFRS standard:
# - mapping  : mapping/income_statement_ifrs.csv
# - ratios   : ratios/ratios_ifrs.toml
# - entries  : data/input/accounting_entries_ifrs.csv
#
# If your project is organized differently, adjust the file paths below.
BASE_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def ifrs_paths() -> dict[str, Path]:
    """Return all relevant file paths for the IFRS standard."""
    return {
        "entries": BASE_DIR / "data" / "input" / "accounting_entries_ifrs.csv",
        "mapping": BASE_DIR / "mapping" / "income_statement_ifrs.csv",
        "ratios": BASE_DIR / "ratios" / "ratios_ifrs.toml",
    }


@pytest.fixture(scope="module")
def ifrs_template(ifrs_paths: dict[str, Path]) -> Template:
    """Load the IFRS mapping template."""
    return Template.from_csv(str(ifrs_paths["mapping"]))


@pytest.fixture(scope="module")
def ifrs_entries(ifrs_paths: dict[str, Path]) -> pd.DataFrame:
    """Load the accounting entries for IFRS."""
    return read_accounting_entries(str(ifrs_paths["entries"]))


@pytest.fixture(scope="module")
def ifrs_statement(
    ifrs_entries: pd.DataFrame,
    ifrs_template: Template,
) -> pd.DataFrame:
    """Aggregate entries into an income-statement-shaped dataframe (IFRS)."""
    return aggregate(ifrs_entries, ifrs_template)


@pytest.fixture(scope="module")
def ifrs_measures(
    ifrs_statement: pd.DataFrame,
    ifrs_template: Template,
) -> dict[str, float]:
    """Compute canonical measures from the aggregated IFRS statement."""
    return build_canonical_measures(ifrs_statement, ifrs_template)


# ---------------------------------------------------------------------------
# 1) Verify the presence of canonical measures in the IFRS mapping
# ---------------------------------------------------------------------------


def test_ifrs_canonical_measures_present(ifrs_template: Template) -> None:
    """Ensure that key canonical measures are defined in the IFRS template."""
    canonical = ifrs_template.canonical_rows()

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
    assert canonical["net_income"].name in {"Net income", "Profit for the period"}


# ---------------------------------------------------------------------------
# 2) Validate key canonical measure values from accounting_entries_ifrs.csv
# ---------------------------------------------------------------------------


def test_ifrs_canonical_measures_values(ifrs_measures: dict[str, float]) -> None:
    """
    Validate key aggregated values for the IFRS dataset.
    If accounting_entries_ifrs.csv changes, these expected values must be updated.
    """
    m = ifrs_measures

    # At this stage, the IFRS dataset is economically identical to CA ASPE / US GAAP,
    # so the values match the canonical measures for those standards.
    assert pytest.approx(m["revenue"], rel=1e-6, abs=0.01) == 170_618.55
    assert pytest.approx(m["cost_of_goods_sold"], rel=1e-6, abs=0.01) == 0.0
    assert pytest.approx(m["gross_margin"], rel=1e-6, abs=0.01) == 170_618.55
    assert (
        pytest.approx(
            m["total_operating_expenses"],
            rel=1e-6,
            abs=0.01,
        )
        == -357_675.81
    )
    assert pytest.approx(m["operating_income"], rel=1e-6, abs=0.01) == -187_057.26
    assert pytest.approx(m["net_income"], rel=1e-6, abs=0.01) == -187_057.26


# ---------------------------------------------------------------------------
# 3) Validate basic ratio computations for IFRS
# ---------------------------------------------------------------------------


def test_ifrs_basic_ratios(
    ifrs_measures: dict[str, float],
    ifrs_paths: dict[str, Path],
) -> None:
    """Validate gross, operating and net margin computations for IFRS."""
    rules_file = ifrs_paths["ratios"]

    # 1) Compute derived measures
    derived = compute_derived_measures(ifrs_measures, rules_file)

    # 2) Compute "basic" ratio set (includes gross, operating, net margins)
    basic_ratios = compute_ratios(derived, rules_file, level="basic")
    ratio_by_key = {r.key: r for r in basic_ratios}

    # Ensure required ratios exist
    assert "gross_margin_pct" in ratio_by_key
    assert "operating_margin_pct" in ratio_by_key
    assert "net_margin_pct" in ratio_by_key

    # Validate computed values (rounded)
    assert (
        pytest.approx(
            ratio_by_key["gross_margin_pct"].value,
            rel=1e-6,
            abs=0.01,
        )
        == 100.0
    )
    assert (
        pytest.approx(
            ratio_by_key["operating_margin_pct"].value,
            rel=1e-6,
            abs=0.01,
        )
        == -109.6348
    )
    assert (
        pytest.approx(
            ratio_by_key["net_margin_pct"].value,
            rel=1e-6,
            abs=0.01,
        )
        == -109.6348
    )
