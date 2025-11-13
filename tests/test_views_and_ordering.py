import pandas as pd
import pytest

from smb_finsight.engine import aggregate
from smb_finsight.mapping import Template
from smb_finsight.views import apply_view_level_filter, build_complete_view


def _is_step10(seq):
    return all(b - a == 10 for a, b in zip(seq, seq[1:]))


@pytest.fixture()
def tpl():
    return Template.from_csv("data/mappings/detailed_income_statement_pcg.csv")


def test_simplified_regular_detailed_views_are_sequential_and_columns(tpl):
    """
    For simplified / regular / detailed:
    - keep the correct levels per view,
    - renumber display_order as 10, 20, 30, ...,
    - columns are ordered as: display_order, id, level, name, type, amount.
    """
    tx = pd.DataFrame(
        [
            # Operating revenues
            {"code": "706000", "amount": 8345.17},  # services
            {"code": "701000", "amount": 16356.48},  # finished goods
            {"code": "703000", "amount": 1903.97},  # residual products
            # Operating expenses
            {"code": "626000", "amount": -11907.79},  # postage & telecom
            {"code": "611000", "amount": -6216.53},  # subcontracting
        ]
    )
    base = aggregate(tx, tpl)

    for view in ("simplified", "regular", "detailed"):
        df = apply_view_level_filter(base, view)

        # Columns order is harmonized
        assert list(df.columns) == [
            "display_order",
            "id",
            "level",
            "name",
            "type",
            "amount",
        ]

        # display_order = 10, 20, 30, ...
        assert len(df) >= 1
        assert df.iloc[0]["display_order"] == 10
        assert _is_step10(df["display_order"].tolist())

        # Level filtering is consistent with the view
        max_level = {"simplified": 1, "regular": 2, "detailed": 3}[view]
        assert int(df["level"].max()) <= max_level


def test_simplified_first_line_is_min_template_order_in_subset(tpl):
    """
    The first line in simplified should be the item with the smallest template
    display_order among rows with level <= 1 (typically "TOTAL Produits
    d'exploitation").
    """
    tx = pd.DataFrame(
        [
            {"code": "706000", "amount": 100.0},
            {"code": "701000", "amount": 50.0},
            {"code": "626000", "amount": -10.0},
        ]
    )
    base = aggregate(tx, tpl)
    sim = apply_view_level_filter(base, "simplified")

    # First line should be at 10, and should be the earliest template-ordered item
    # in the subset
    assert sim.iloc[0]["display_order"] == 10
    assert "Produits d'exploitation" in str(sim.iloc[0]["name"])


def test_complete_view_children_immediately_after_parent_and_sequential(tpl):
    """
    In the complete view:
    - account children must appear immediately after their level-3 parent,
    - display_order must be strictly 10-stepped,
    - columns order is harmonized.
    """
    tx = pd.DataFrame(
        [
            {"code": "707000", "amount": 2494.29},  # child of "Ventes de marchandises"
            {"code": "706000", "amount": 8345.17},  # separate parent "Prestations de
            # services"
        ]
    )
    name_by_code = {"707000": "", "706000": ""}

    base = aggregate(tx, tpl)
    complete = build_complete_view(base, tx, tpl, name_by_code)

    # Columns order
    assert list(complete.columns) == [
        "display_order",
        "id",
        "level",
        "name",
        "type",
        "amount",
    ]

    # display_order = 10, 20, 30, ...
    assert complete.iloc[0]["display_order"] == 10
    assert _is_step10(complete["display_order"].tolist())

    # Find parent "Ventes de marchandises" (level 3)
    parent_idx = complete.index[complete["name"] == "Ventes de marchandises"]
    assert len(parent_idx) == 1, "Parent 'Ventes de marchandises' not found"
    pi = int(parent_idx[0])

    # Its first child must be right after, level + 1, and start with the account code
    assert complete.iloc[pi + 1]["level"] == complete.iloc[pi]["level"] + 1
    assert str(complete.iloc[pi + 1]["name"]).startswith("707000")

    # The next parent (e.g., 'Prestations de services') must come after the child
    assert (
        complete.iloc[pi + 2]["display_order"]
        == complete.iloc[pi + 1]["display_order"] + 10
    )
