"""Minimal data contracts for the KPI layer.

Every public KPI function validates its input before computing anything. The point is not
ceremony: a service indicator computed on a frame with a text column where a quantity should
be, or with silently missing timestamps, is worse than no indicator at all, because it is
reported with the same confidence as a correct one.

Validation collects every problem before raising, so a malformed extract is diagnosed in one
pass instead of one column per run.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd
from pandas.api import types as pdt

Kind = Literal["string", "integer", "float", "numeric", "datetime", "boolean"]


class ContractError(ValueError):
    """Raised when a frame does not satisfy a contract."""


@dataclass(frozen=True)
class Column:
    """Expectation for a single column.

    Attributes:
        name: Column name.
        kind: Expected logical type.
        required: Whether the column must be present.
        nullable: Whether nulls are allowed.
        non_negative: Whether negative values are rejected (numeric kinds only).
    """

    name: str
    kind: Kind
    required: bool = True
    nullable: bool = False
    non_negative: bool = False

    def check_kind(self, series: pd.Series) -> str | None:
        """Return a problem description, or ``None`` when the type is acceptable."""
        checks = {
            "string": lambda s: pdt.is_string_dtype(s) or pdt.is_object_dtype(s),
            "integer": pdt.is_integer_dtype,
            "float": pdt.is_float_dtype,
            "numeric": pdt.is_numeric_dtype,
            "datetime": pdt.is_datetime64_any_dtype,
            "boolean": pdt.is_bool_dtype,
        }
        if isinstance(series.dtype, pd.CategoricalDtype):
            series = series.astype(series.cat.categories.dtype)
        if not checks[self.kind](series):
            return f"{self.name!r}: expected {self.kind}, found dtype {series.dtype}"
        return None


@dataclass(frozen=True)
class Contract:
    """A named set of column expectations.

    Attributes:
        name: Contract name, used in error messages.
        columns: Expected columns.
        unique: Columns whose combination must be unique, if any.
    """

    name: str
    columns: tuple[Column, ...]
    unique: tuple[str, ...] = field(default=())

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(c.name for c in self.columns)

    def validate(self, df: pd.DataFrame, *, subset: Sequence[str] | None = None) -> pd.DataFrame:
        """Validate ``df`` and return it unchanged.

        Args:
            df: Frame to validate.
            subset: Restrict validation to these contract columns. Use it when a KPI only
                depends on part of the contract, so callers are not forced to carry columns
                they do not have.

        Returns:
            The same frame, so validation can be inlined in a pipeline.

        Raises:
            ContractError: If any expectation is violated. The message lists every problem.
        """
        if not isinstance(df, pd.DataFrame):
            raise ContractError(f"{self.name}: expected a DataFrame, got {type(df).__name__}")

        wanted = self.columns
        if subset is not None:
            requested = set(subset)
            unknown = requested - set(self.column_names)
            if unknown:
                raise ContractError(f"{self.name}: unknown columns in subset {sorted(unknown)}")
            wanted = tuple(c for c in self.columns if c.name in requested)

        problems: list[str] = []
        for col in wanted:
            if col.name not in df.columns:
                if col.required:
                    problems.append(f"{col.name!r}: missing required column")
                continue

            series = df[col.name]
            kind_problem = col.check_kind(series)
            if kind_problem:
                problems.append(kind_problem)
                continue
            if not col.nullable and series.isna().any():
                n = int(series.isna().sum())
                problems.append(f"{col.name!r}: {n} null value(s) where nulls are not allowed")
            if col.non_negative and col.kind in {"integer", "float", "numeric"}:
                negatives = int((series.dropna() < 0).sum())
                if negatives:
                    problems.append(f"{col.name!r}: {negatives} negative value(s)")

        if self.unique and all(c in df.columns for c in self.unique):
            duplicated = int(df.duplicated(subset=list(self.unique)).sum())
            if duplicated:
                problems.append(
                    f"{list(self.unique)}: {duplicated} duplicated row(s); this key must be unique"
                )

        if problems:
            bullets = "\n".join(f"  - {p}" for p in problems)
            raise ContractError(f"{self.name}: {len(problems)} problem(s)\n{bullets}")
        return df


ORDER_LINES = Contract(
    name="order_lines",
    columns=(
        Column("order_id", "string"),
        Column("line_id", "string"),
        Column("site", "string"),
        Column("sku", "string"),
        Column("order_ts", "datetime"),
        Column("promised_ts", "datetime"),
        Column("qty_ordered", "integer", non_negative=True),
        Column("qty_shipped", "integer", non_negative=True),
        Column("qty_delivered", "integer", non_negative=True),
        Column("ship_ts", "datetime", nullable=True),
        Column("delivered_ts", "datetime", nullable=True),
        Column("status", "string"),
    ),
    unique=("line_id",),
)

RECEIPTS = Contract(
    name="receipts",
    columns=(
        Column("receipt_id", "string"),
        Column("site", "string"),
        Column("carrier", "string", required=False),
        Column("appointment_ts", "datetime", required=False, nullable=True),
        Column("arrival_ts", "datetime"),
        Column("unload_start_ts", "datetime"),
        Column("unload_end_ts", "datetime"),
        Column("putaway_end_ts", "datetime"),
        Column("pallets", "integer", required=False, non_negative=True),
    ),
    unique=("receipt_id",),
)

CYCLE_COUNTS = Contract(
    name="cycle_counts",
    columns=(
        Column("count_date", "datetime"),
        Column("site", "string"),
        Column("location", "string"),
        Column("sku", "string", required=False),
        Column("system_qty", "numeric", non_negative=True),
        Column("counted_qty", "numeric", non_negative=True),
    ),
)
