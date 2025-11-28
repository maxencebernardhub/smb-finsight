from datetime import date
from types import SimpleNamespace

import pandas as pd

import smb_finsight.multi_periods as mp
from smb_finsight.engine import MeasureMeta
from smb_finsight.periods import Period
from smb_finsight.ratios import RatioResult


def _make_app_and_standard(tmp_path):
    """
    Build minimal app_config and standard_config objects for testing.

    We use SimpleNamespace instead of the real AppConfig/StandardConfig
    dataclasses to keep the tests focused on the orchestration logic.
    """
    app_config = SimpleNamespace(
        # Not used directly in tests because load_entries is monkeypatched.
        database=SimpleNamespace(),
        balance_sheet_inputs={"equity": 500.0},
        hr_inputs={"headcount": 10.0},
        period_days=365,
        ratios_enabled=True,
        ratios_level="basic",
    )

    # Paths are not used by the stubs, they only need to be non-None.
    standard_config = SimpleNamespace(
        standard="FR_PCG",
        income_statement_mapping=tmp_path / "dummy_mapping.csv",
        secondary_mapping=None,
        chart_of_accounts=None,
        ratios_rules_file=tmp_path / "dummy_rules.toml",
        ratios_custom_file=None,
    )

    return app_config, standard_config


def _install_stubs(monkeypatch):
    """
    Install stubs for the heavy dependencies used by compute_all_multi_period.

    We stub:
    - load_entries
    - Template.from_csv
    - aggregate
    - build_canonical_measures
    - build_canonical_measures_metadata
    - load_derived_measures_metadata
    - compute_derived_measures
    - compute_ratios
    """

    # ---- load_entries: return an empty but well-formed DataFrame ----------
    def stub_load_entries(cfg, start, end):
        return pd.DataFrame(
            {
                "date": pd.to_datetime([]),
                "code": [],
                "description": [],
                "amount": [],
            }
        )

    monkeypatch.setattr(mp, "load_entries", stub_load_entries)

    # ---- Template.from_csv: provide two dummy rows with notes --------------
    class DummyRow:
        def __init__(self, row_id, name, level, display_order, notes=""):
            self.id = row_id
            self.name = name
            self.level = level
            self.display_order = display_order
            self.type = "acc"
            self.canonical_measure = None
            self.include = ""
            self.exclude = ""
            self.formula = ""
            self.notes = notes

    class DummyTemplate:
        def __init__(self, rows):
            self.rows = rows

    def stub_template_from_csv(path: str):
        rows = [
            DummyRow(1, "Revenue", 0, 10, notes="Revenue notes"),
            DummyRow(2, "Expenses", 0, 20, notes="Expenses notes"),
        ]
        return DummyTemplate(rows)

    monkeypatch.setattr(mp.Template, "from_csv", staticmethod(stub_template_from_csv))

    # ---- aggregate: build a statement DataFrame from template rows ---------
    def stub_aggregate(accounting_entries, template):
        data = [
            {
                "level": row.level,
                "display_order": row.display_order,
                "id": row.id,
                "name": row.name,
                "type": row.type,
                "amount": 100.0 * row.id,
            }
            for row in template.rows
        ]
        return pd.DataFrame(data)

    monkeypatch.setattr(mp, "aggregate", stub_aggregate)

    # ---- build_canonical_measures: fixed base + extra_measures ------------
    def stub_build_canonical_measures(statement, template, extra_measures=None):
        base = {"revenue": 1000.0, "expenses": 400.0}
        if extra_measures:
            base.update(extra_measures)
        return base

    monkeypatch.setattr(mp, "build_canonical_measures", stub_build_canonical_measures)

    # ---- build_canonical_measures_metadata: metadata for canonical measures
    def stub_build_canonical_measures_metadata(template):
        return {
            "revenue": MeasureMeta(
                key="revenue",
                label="Revenue",
                unit="amount",
                notes="Meta revenue",
                kind="canonical",
            ),
            "expenses": MeasureMeta(
                key="expenses",
                label="Expenses",
                unit="amount",
                notes="Meta expenses",
                kind="canonical",
            ),
        }

    monkeypatch.setattr(
        mp, "build_canonical_measures_metadata", stub_build_canonical_measures_metadata
    )

    # ---- load_derived_measures_metadata: metadata for derived measures -----
    def stub_load_derived_measures_metadata(path):
        return {
            "gross_profit": MeasureMeta(
                key="gross_profit",
                label="Gross profit",
                unit="amount",
                notes="Meta gross profit",
                kind="extra",
            )
        }

    monkeypatch.setattr(
        mp, "load_derived_measures_metadata", stub_load_derived_measures_metadata
    )

    # ---- compute_derived_measures: add one derived measure -----------------
    def stub_compute_derived_measures(base_measures, rules_file):
        out = dict(base_measures)
        if "revenue" in base_measures and "expenses" in base_measures:
            out["gross_profit"] = base_measures["revenue"] - base_measures["expenses"]
        return out

    monkeypatch.setattr(mp, "compute_derived_measures", stub_compute_derived_measures)

    # ---- compute_ratios: one dummy ratio using the provided level ----------
    def stub_compute_ratios(all_measures, rules_file, level: str):
        return [
            RatioResult(
                key="gross_margin_pct",
                label="Gross margin %",
                value=0.6,
                unit="percent",
                notes="Dummy ratio",
                level=level,
            )
        ]

    monkeypatch.setattr(mp, "compute_ratios", stub_compute_ratios)


def test_compute_all_multi_period_returns_structures(monkeypatch, tmp_path):
    """
    Basic smoke test: ensure compute_all_multi_period returns the expected
    dataclasses and that the primary statement contains data for all periods.
    """
    _install_stubs(monkeypatch)
    app_config, standard_config = _make_app_and_standard(tmp_path)

    periods = [
        Period(start=date(2025, 1, 1), end=date(2025, 1, 31), label="2025-01"),
        Period(start=date(2025, 2, 1), end=date(2025, 2, 28), label="2025-02"),
    ]

    statements, measures, ratios = mp.compute_all_multi_period(
        app_config=app_config,
        standard_config=standard_config,
        periods=periods,
    )

    assert isinstance(statements, mp.StatementsMultiPeriod)
    assert isinstance(measures, mp.MeasuresMultiPeriod)
    assert isinstance(ratios, mp.RatiosMultiPeriod)

    # 2 periods * 2 rows (Revenue, Expenses) = 4 rows in primary.
    assert len(statements.primary) == 4
    assert set(statements.primary["period_label"]) == {"2025-01", "2025-02"}


def test_statements_primary_have_expected_columns_and_notes(monkeypatch, tmp_path):
    """
    Check that the primary statement DataFrame has the expected columns
    and that notes are correctly attached based on mapping row IDs.
    """
    _install_stubs(monkeypatch)
    app_config, standard_config = _make_app_and_standard(tmp_path)

    periods = [
        Period(start=date(2025, 1, 1), end=date(2025, 1, 31), label="2025-01"),
    ]

    statements, _, _ = mp.compute_all_multi_period(
        app_config=app_config,
        standard_config=standard_config,
        periods=periods,
    )

    expected_cols = {
        "period_label",
        "level",
        "display_order",
        "id",
        "name",
        "type",
        "amount",
        "notes",
    }
    assert set(statements.primary.columns) == expected_cols

    # Notes should come from the DummyRow definitions.
    notes = set(statements.primary["notes"])
    assert "Revenue notes" in notes
    assert "Expenses notes" in notes


def test_measures_include_canonical_derived_and_extra(monkeypatch, tmp_path):
    """
    Ensure that compute_all_multi_period produces measures that combine:
    - canonical measures (revenue, expenses),
    - derived measures (gross_profit),
    - extra measures (equity, headcount, period_days).
    """
    _install_stubs(monkeypatch)
    app_config, standard_config = _make_app_and_standard(tmp_path)

    periods = [
        Period(start=date(2025, 1, 1), end=date(2025, 1, 31), label="2025-01"),
    ]

    _, measures, _ = mp.compute_all_multi_period(
        app_config=app_config,
        standard_config=standard_config,
        periods=periods,
    )

    df = measures.data
    keys = set(df["measure_key"])

    # From stub_build_canonical_measures
    assert "revenue" in keys
    assert "expenses" in keys

    # From stub_compute_derived_measures
    assert "gross_profit" in keys

    # From app_config.extra_measures
    assert "equity" in keys
    assert "headcount" in keys
    assert "period_days" in keys

    # Check metadata for one canonical, one derived, one extra
    revenue_row = df[df["measure_key"] == "revenue"].iloc[0]
    assert revenue_row["label"] == "Revenue"
    assert revenue_row["unit"] == "amount"
    assert revenue_row["kind"] == "canonical"

    gross_profit_row = df[df["measure_key"] == "gross_profit"].iloc[0]
    assert gross_profit_row["label"] == "Gross profit"
    assert gross_profit_row["kind"] == "extra"

    period_days_row = df[df["measure_key"] == "period_days"].iloc[0]
    assert period_days_row["unit"] == "days"
    assert period_days_row["kind"] == "extra"


def test_ratios_have_period_label_and_level(monkeypatch, tmp_path):
    """
    Ensure that ratios returned by compute_all_multi_period contain
    the expected keys, period_label and respect the ratios_level
    configured in app_config.
    """
    _install_stubs(monkeypatch)
    app_config, standard_config = _make_app_and_standard(tmp_path)
    app_config.ratios_level = "advanced"

    periods = [
        Period(start=date(2025, 1, 1), end=date(2025, 1, 31), label="2025-01"),
        Period(start=date(2025, 2, 1), end=date(2025, 2, 28), label="2025-02"),
    ]

    _, _, ratios = mp.compute_all_multi_period(
        app_config=app_config,
        standard_config=standard_config,
        periods=periods,
    )

    df = ratios.data
    assert not df.empty

    # One ratio per period in the stub.
    assert len(df) == len(periods)

    assert set(df["period_label"]) == {"2025-01", "2025-02"}
    assert set(df["key"]) == {"gross_margin_pct"}

    # The level should match app_config.ratios_level passed to compute_ratios.
    assert set(df["level"]) == {"advanced"}
