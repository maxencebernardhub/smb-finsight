from datetime import date

import pandas as pd

import smb_finsight.periods as periods


def test_filter_entries_by_period_inclusive_bounds() -> None:
    """filter_entries_by_period should keep entries with dates in [start, end]."""
    df = pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2025-01-01", "2025-02-15", "2025-03-10", "2025-04-01", "2025-05-01"]
            ),
            "code": ["701000", "701000", "607000", "607000", "701000"],
            "description": ["A", "B", "C", "D", "E"],
            "amount": [10, 20, -5, -15, 30],
        }
    )

    p = periods.Period(
        start=date(2025, 2, 1),
        end=date(2025, 4, 1),
        label="Test period",
    )

    filtered = periods.filter_entries_by_period(df, p)

    assert len(filtered) == 3
    assert filtered["date"].min() == pd.Timestamp("2025-02-15")
    assert filtered["date"].max() == pd.Timestamp("2025-04-01")
