from pathlib import Path

import pandas as pd
import pytest

from smb_finsight.engine import aggregate, build_canonical_measures
from smb_finsight.io import read_accounting_entries
from smb_finsight.mapping import Template
from smb_finsight.ratios import compute_derived_measures, compute_ratios

# The tests assume the default file structure used for the CA ASPE standard:
# - mapping  : mapping/income_statement_ca_aspe.csv
# - ratios   : ratios/ratios_ca_aspe.toml
# - entries  : data/input/accounting_entries_ca_aspe.csv
#
# If your project is organized differently, adjust the file paths below.
BASE_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def ca_aspe_paths() -> dict[str, Path]:
    """Return all relevant file paths for the CA ASPE standard."""
    return {
        "entries": BASE_DIR / "data" / "input" / "accounting_entries_ca_aspe.csv",
        "mapping": BASE_DIR / "mapping" / "income_statement_ca_aspe.csv",
        "ratios": BASE_DIR / "ratios" / "ratios_ca_aspe.toml",
    }


@pytest.fixture(scope="module")
def ca_aspe_template(ca_aspe_paths: dict[str, Path]) -> Template:
    """Load the CA ASPE mapping template."""
    return Template.from_csv(str(ca_aspe_paths["mapping"]))


@pytest.fixture(scope="module")
def ca_aspe_entries(ca_aspe_paths: dict[str, Path]) -> pd.DataFrame:
    """Load the accounting entries for CA ASPE."""
    return read_accounting_entries(str(ca_aspe_paths["entries"]))


@pytest.fixture(scope="module")
def ca_aspe_statement(
    ca_aspe_entries: pd.DataFrame,
    ca_aspe_template: Template,
) -> pd.DataFrame:
    """Aggregate entries into an income-statement-shaped dataframe."""
    return aggregate(ca_aspe_entries, ca_aspe_template)


@pytest.fixture(scope="module")
def ca_aspe_measures(
    ca_aspe_statement: pd.DataFrame, ca_aspe_template: Template
) -> dict[str, float]:
    """Compute canonical measures from the aggregated CA ASPE statement."""
    return build_canonical_measures(ca_aspe_statement, ca_aspe_template)


# ---------------------------------------------------------------------------
# 1) Verify the presence of canonical measures in the CA ASPE mapping
# ---------------------------------------------------------------------------


def test_ca_aspe_canonical_measures_present(ca_aspe_template: Template) -> None:
    """Ensure that key canonical measures are defined in the CA ASPE template."""
    canonical = ca_aspe_template.canonical_rows()

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
# 2) Validate key canonical measure values from accounting_entries_ca_aspe.csv
# ---------------------------------------------------------------------------


def test_ca_aspe_canonical_measures_values(ca_aspe_measures: dict[str, float]) -> None:
    """
    Validate key aggregated values for the CA ASPE dataset.
    If accounting_entries_ca_aspe.csv changes, these expected values must be updated.
    """
    m = ca_aspe_measures

    assert pytest.approx(m["revenue"], rel=1e-6, abs=0.01) == 170_618.55
    assert pytest.approx(m["cost_of_goods_sold"], rel=1e-6, abs=0.01) == 0.0
    assert pytest.approx(m["gross_margin"], rel=1e-6, abs=0.01) == 170_618.55
    assert (
        pytest.approx(m["total_operating_expenses"], rel=1e-6, abs=0.01) == -357_675.81
    )
    assert pytest.approx(m["operating_income"], rel=1e-6, abs=0.01) == -187_057.26
    assert pytest.approx(m["net_income"], rel=1e-6, abs=0.01) == -187_057.26


# ---------------------------------------------------------------------------
# 3) Validate basic ratio computations for CA ASPE
# ---------------------------------------------------------------------------


def test_ca_aspe_basic_ratios(
    ca_aspe_measures: dict[str, float], ca_aspe_paths: dict[str, Path]
) -> None:
    """Validate gross, operating and net margin computations for CA ASPE."""
    rules_file = ca_aspe_paths["ratios"]

    # 1) Compute derived measures
    derived = compute_derived_measures(ca_aspe_measures, rules_file)

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

    # Optional label consistency checks
    assert ratio_by_key["gross_margin_pct"].label == "Gross margin (%)"
    assert ratio_by_key["operating_margin_pct"].label == "Operating margin (%)"
    assert ratio_by_key["net_margin_pct"].label == "Net margin (%)"
