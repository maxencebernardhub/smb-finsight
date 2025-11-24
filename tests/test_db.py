from datetime import date

import pandas as pd

from smb_finsight.db import (
    DatabaseConfig,
    has_entries,
    import_entries,
    init_database,
    list_import_batches,
    load_entries,
)


def make_tmp_db_cfg(tmp_path) -> DatabaseConfig:
    """Helper to build a DatabaseConfig pointing to a temporary SQLite file."""
    db_path = tmp_path / "test_db.sqlite"
    return DatabaseConfig(engine="sqlite", path=db_path)


def test_init_database_creates_file_and_schema(tmp_path):
    """init_database should create the SQLite file and an empty schema."""
    cfg = make_tmp_db_cfg(tmp_path)

    assert not cfg.path.exists()
    init_database(cfg)
    assert cfg.path.exists()

    # A freshly initialized database should not contain any entries.
    assert has_entries(cfg) is False


def test_import_and_load_entries_basic_flow(tmp_path):
    """Basic round-trip: import entries, then load them for a period."""
    cfg = make_tmp_db_cfg(tmp_path)
    init_database(cfg)

    df = pd.DataFrame(
        [
            {
                "date": date(2025, 1, 1),
                "code": "701",
                "description": "Sale A",
                "amount": 1000.0,
            },
            {
                "date": date(2025, 1, 15),
                "code": "607",
                "description": "Purchase B",
                "amount": -300.0,
            },
        ]
    )

    stats = import_entries(df, cfg, source_type="csv", source_label="test.csv")
    assert stats.rows_inserted == 2
    assert stats.duplicates_detected == 0
    assert has_entries(cfg) is True

    # Period covering the whole month of January 2025
    df_loaded = load_entries(cfg, date(2025, 1, 1), date(2025, 1, 31))
    assert len(df_loaded) == 2
    assert set(df_loaded.columns) == {"date", "code", "description", "amount"}

    # Amounts should be reconstructed correctly from integer cents
    amount_sale = float(df_loaded.loc[df_loaded["code"] == "701", "amount"].iloc[0])
    amount_purchase = float(df_loaded.loc[df_loaded["code"] == "607", "amount"].iloc[0])
    assert amount_sale == 1000.0
    assert amount_purchase == -300.0


def test_import_detects_duplicates(tmp_path):
    """Re-importing the same entry should create a duplicate record."""
    cfg = make_tmp_db_cfg(tmp_path)
    init_database(cfg)

    df = pd.DataFrame(
        [
            {
                "date": date(2025, 1, 1),
                "code": "701",
                "description": "Sale A",
                "amount": 1000.0,
            },
        ]
    )

    stats1 = import_entries(df, cfg, source_type="csv", source_label="batch1.csv")
    assert stats1.rows_inserted == 1
    assert stats1.duplicates_detected == 0

    # Re-import the exact same entry
    stats2 = import_entries(df, cfg, source_type="csv", source_label="batch2.csv")
    assert stats2.rows_inserted == 0
    assert stats2.duplicates_detected == 1

    # There should be two import batches recorded
    batches = list_import_batches(cfg)
    assert len(batches) == 2
    assert set(batches.columns) == {
        "id",
        "created_at",
        "source_type",
        "source_label",
        "rows_inserted",
    }
