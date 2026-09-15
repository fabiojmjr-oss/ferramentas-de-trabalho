"""Data contract behaviour."""

from __future__ import annotations

import pandas as pd
import pytest

from oplab.kpi import CYCLE_COUNTS, ORDER_LINES, RECEIPTS, Column, Contract, ContractError

SIMPLE = Contract(
    name="simple",
    columns=(
        Column("id", "string"),
        Column("qty", "integer", non_negative=True),
        Column("ts", "datetime", nullable=True),
        Column("note", "string", required=False),
    ),
    unique=("id",),
)


def _valid() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "id": ["a", "b"],
            "qty": [1, 2],
            "ts": pd.to_datetime(["2025-01-01", None]),
        }
    )


def test_valid_frame_passes_through_unchanged() -> None:
    frame = _valid()
    assert SIMPLE.validate(frame) is frame


def test_every_problem_is_reported_in_one_pass() -> None:
    frame = _valid().assign(qty=[-1, -2]).drop(columns=["id"])
    with pytest.raises(ContractError) as excinfo:
        SIMPLE.validate(frame)
    message = str(excinfo.value)
    assert "2 problem(s)" in message
    assert "missing required column" in message
    assert "negative value" in message


def test_wrong_dtype_is_reported_without_masking_other_checks() -> None:
    frame = _valid().assign(qty=["one", "two"])
    with pytest.raises(ContractError, match="expected integer"):
        SIMPLE.validate(frame)


def test_nulls_rejected_only_where_disallowed() -> None:
    SIMPLE.validate(_valid())  # ts is nullable
    with pytest.raises(ContractError, match="null value"):
        SIMPLE.validate(_valid().assign(qty=[1, None]).astype({"qty": "Int64"}))


def test_duplicate_key_is_reported() -> None:
    with pytest.raises(ContractError, match="duplicated row"):
        SIMPLE.validate(_valid().assign(id=["a", "a"]))


def test_optional_column_may_be_absent() -> None:
    SIMPLE.validate(_valid())


def test_subset_limits_validation_to_the_columns_in_use() -> None:
    partial = _valid()[["id", "qty"]]
    SIMPLE.validate(partial, subset=["id", "qty"])
    with pytest.raises(ContractError, match="missing required column"):
        SIMPLE.validate(partial)


def test_subset_rejects_unknown_column_names() -> None:
    with pytest.raises(ContractError, match="unknown columns"):
        SIMPLE.validate(_valid(), subset=["id", "nope"])


def test_categorical_columns_satisfy_their_underlying_kind() -> None:
    frame = _valid().assign(id=pd.Categorical(["a", "b"]))
    SIMPLE.validate(frame)


def test_non_dataframe_input_is_rejected() -> None:
    with pytest.raises(ContractError, match="expected a DataFrame"):
        SIMPLE.validate([1, 2, 3])  # type: ignore[arg-type]


def test_generated_tables_satisfy_their_contracts(dataset) -> None:  # type: ignore[no-untyped-def]
    ORDER_LINES.validate(dataset.order_lines)
    RECEIPTS.validate(dataset.receipts)
    CYCLE_COUNTS.validate(dataset.cycle_counts)
