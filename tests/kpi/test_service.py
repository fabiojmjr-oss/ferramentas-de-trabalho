"""Service indicators, checked against a hand-computed fixture.

Every expected value in this module was derived by hand from the table in
``tests/conftest.py``. That is deliberate: a service metric tested only against its own
implementation tests nothing.
"""

from __future__ import annotations

import pandas as pd
import pytest

from oplab.kpi import (
    ServicePolicy,
    fill_rate,
    in_full_rate,
    line_service,
    on_time_rate,
    otif,
    service_sensitivity,
)


def test_default_policy_excludes_cancelled_and_undelivered(order_lines: pd.DataFrame) -> None:
    evaluated = line_service(order_lines)
    in_scope = evaluated.set_index("line_id")["in_scope"]
    assert in_scope["O1-L1"]
    assert not in_scope["O3-L1"], "cancelled lines must leave the denominator"
    assert not in_scope["O3-L2"], "undelivered lines are excluded by default"
    assert int(in_scope.sum()) == 4


def test_headline_rates(order_lines: pd.DataFrame) -> None:
    assert on_time_rate(order_lines) == pytest.approx(0.75)
    assert in_full_rate(order_lines) == pytest.approx(0.75)
    # O1-L1 and O2-L2 only: O1-L2 is short and O2-L1 is late.
    assert otif(order_lines) == pytest.approx(0.50)


def test_open_lines_counted_as_failures_lower_the_result(order_lines: pd.DataFrame) -> None:
    strict = ServicePolicy(open_treatment="fail")
    evaluated = line_service(order_lines, strict)
    assert int(evaluated["in_scope"].sum()) == 5
    assert otif(order_lines, strict) == pytest.approx(2 / 5)


def test_grace_period_rescues_the_late_line(order_lines: pd.DataFrame) -> None:
    # O2-L1 is eight hours late, so a ten-hour grace makes every in-scope line on time.
    generous = ServicePolicy(grace_minutes=10 * 60)
    assert on_time_rate(order_lines, generous) == pytest.approx(1.0)
    assert otif(order_lines, generous) == pytest.approx(0.75)


def test_in_full_tolerance_rescues_the_short_line(order_lines: pd.DataFrame) -> None:
    # O1-L2 delivered 4 of 5, so anything above a 20% tolerance counts it as complete.
    tolerant = ServicePolicy(in_full_tolerance=0.25)
    assert in_full_rate(order_lines, tolerant) == pytest.approx(1.0)


def test_the_three_fill_rate_bases_disagree_on_the_same_data(order_lines: pd.DataFrame) -> None:
    assert fill_rate(order_lines, "unit") == pytest.approx(24 / 25)
    assert fill_rate(order_lines, "line") == pytest.approx(0.75)
    # O2 is complete, O1 is not; O3 is out of scope entirely.
    assert fill_rate(order_lines, "order") == pytest.approx(0.50)


def test_fill_rate_rejects_unknown_basis(order_lines: pd.DataFrame) -> None:
    with pytest.raises(ValueError, match="unknown basis"):
        fill_rate(order_lines, "weight")  # type: ignore[arg-type]


def test_grouping_by_site(order_lines: pd.DataFrame) -> None:
    by_site = otif(order_lines, by="site")
    assert by_site["CD-SP"] == pytest.approx(0.5)
    assert by_site["CD-RJ"] == pytest.approx(0.5)


def test_sensitivity_spread_is_reported(order_lines: pd.DataFrame) -> None:
    table = service_sensitivity(order_lines)
    assert list(table["policy"]) == ["strict", "standard", "grace_1day", "tolerant_5pct"]
    assert table["otif"].is_monotonic_increasing, "looser conventions cannot lower OTIF"
    assert table.loc[0, "lines_in_scope"] > table.loc[1, "lines_in_scope"]
    assert table["definition"].str.len().gt(0).all()


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"grace_minutes": -1}, "grace_minutes"),
        ({"in_full_tolerance": 1.0}, "in_full_tolerance"),
        ({"open_treatment": "ignore"}, "open_treatment"),
    ],
)
def test_policy_validates_its_arguments(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        ServicePolicy(**kwargs)  # type: ignore[arg-type]


def test_real_dataset_rates_are_bounded(dataset) -> None:  # type: ignore[no-untyped-def]
    value = otif(dataset.order_lines)
    assert 0.0 < value < 1.0
