import types
from datetime import date

import pandas as pd

import smb_finsight.periods as periods
from smb_finsight.config import FiscalYear


def _args(period=None, from_date=None, to_date=None):
    """Small helper to simulate argparse.Namespace."""
    return types.SimpleNamespace(
        period=period,
        from_date=from_date,
        to_date=to_date,
    )


def test_period_fy_basic():
    fy = FiscalYear(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    p = periods.period_fy(fy)
    assert p.start == fy.start_date
    assert p.end == fy.end_date
    assert ("FY" in p.label) or ("Fiscal year" in p.label)


def test_period_ytd_inside_fy(monkeypatch):
    fy = FiscalYear(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))

    # Fix "today" to 2025-11-15
    monkeypatch.setattr(periods, "_today", lambda: date(2025, 11, 15))

    p = periods.period_ytd(fy)
    assert p.start == date(2025, 1, 1)
    assert p.end == date(2025, 11, 15)
    assert "Year" in p.label or "date" in p.label


def test_period_mtd_inside_fy(monkeypatch):
    fy = FiscalYear(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    monkeypatch.setattr(periods, "_today", lambda: date(2025, 11, 15))

    p = periods.period_mtd(fy)
    assert p.start == date(2025, 11, 1)
    assert p.end == date(2025, 11, 15)


def test_period_last_month_clamped_to_fy(monkeypatch):
    fy = FiscalYear(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    # today = 2025-02-10 → last month = 2025-01-01
    # → 2025-01-31 (entièrement dans l'exercice)
    monkeypatch.setattr(periods, "_today", lambda: date(2025, 2, 10))

    p = periods.period_last_month(fy)
    assert p.start == date(2025, 1, 1)
    assert p.end == date(2025, 1, 31)
    assert "Last month" in p.label or "month" in p.label


def test_period_last_fy_shape(monkeypatch):
    fy = FiscalYear(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    p = periods.period_last_fy(fy)
    assert p.start == date(2024, 1, 1)
    assert p.end == date(2024, 12, 31)


def test_determine_period_from_args_predefined(monkeypatch):
    fy = FiscalYear(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))
    monkeypatch.setattr(periods, "_today", lambda: date(2025, 11, 20))

    p_ytd = periods.determine_period_from_args(_args(period="ytd"), fy)
    assert p_ytd.start == date(2025, 1, 1)
    assert p_ytd.end == date(2025, 11, 20)

    p_mtd = periods.determine_period_from_args(_args(period="mtd"), fy)
    assert p_mtd.start == date(2025, 11, 1)
    assert p_mtd.end == date(2025, 11, 20)


def test_determine_period_custom_from_to_overrides_fy():
    fy = FiscalYear(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))

    p = periods.determine_period_from_args(
        _args(from_date="2025-03-10", to_date="2025-04-05"), fy
    )
    assert p.start == date(2025, 3, 10)
    assert p.end == date(2025, 4, 5)
    assert "Custom" in p.label or "period" in p.label


def test_determine_period_custom_missing_end_defaults_to_fy_end():
    fy = FiscalYear(start_date=date(2025, 1, 1), end_date=date(2025, 12, 31))

    p = periods.determine_period_from_args(
        _args(from_date="2025-03-10", to_date=None), fy
    )
    assert p.start == date(2025, 3, 10)
    assert p.end == fy.end_date


def test_filter_entries_by_period():
    # Simple dataframe with 5 dates
    data = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2025-01-01",
                    "2025-02-15",
                    "2025-03-10",
                    "2025-04-01",
                    "2025-05-20",
                ]
            ),
            "code": ["600000", "600000", "700000", "700000", "600000"],
            "description": ["A", "B", "C", "D", "E"],
            "amount": [10, 20, 30, 40, 50],
        }
    )

    p = periods.Period(start=date(2025, 2, 1), end=date(2025, 4, 1), label="test")
    filtered = periods.filter_entries_by_period(data, p)

    assert len(filtered) == 3
    assert filtered["date"].min() == pd.Timestamp("2025-02-15")
    assert filtered["date"].max() == pd.Timestamp("2025-04-01")
