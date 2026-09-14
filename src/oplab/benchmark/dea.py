"""Data envelopment analysis, and the reason it usually cannot be used on a small network.

DEA measures relative efficiency with several inputs and several outputs at once, without
requiring a price for any of them. It does that by letting **each unit choose the weights that
flatter it most**, and reporting how far the unit still is from the best combination anyone
achieved. That construction is its strength and its trap.

The trap is dimensional. Every input and output adds a degree of freedom the units can use to
excuse themselves, so with enough measures relative to the number of units, everybody is
efficient and the method says nothing. The rules of thumb in the literature are
``n >= 3 x (m + s)`` and ``n >= m x s``, where ``n`` is units, ``m`` inputs and ``s`` outputs.

A four-site network with two inputs and two outputs needs at least twelve units and has four.
Measured on the bundled data it puts three of the four on the frontier under variable returns
to scale and two of four under constant returns - weak discrimination either way, and not
because the sites are equally good. What that shortage of units mainly does is hand the
*modelling choice* more influence than the data: the same site scores 0.89 under variable
returns and 0.63 under constant returns, and most of that 27-point difference is a penalty for
being small rather than a measure of how it is run. :func:`discrimination_check` says so before
the scores are read, which is the difference between using DEA and being used by it.

The usual way out is to raise ``n`` rather than lower ``m + s``: treat site-months as the units
of analysis instead of sites. Forty-eight site-months clear the threshold comfortably, and the
efficiency scores start to discriminate. What that costs is interpretation - a site-month is
efficient relative to other site-months including its own, so the result is about consistency
over time as much as about the site.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd
from ortools.linear_solver import pywraplp

TOLERANCE = 1e-6


@dataclass(frozen=True)
class DiscriminationCheck:
    """Whether a DEA run can discriminate at all.

    Attributes:
        units: Number of decision-making units.
        inputs: Number of input measures.
        outputs: Number of output measures.
        minimum_units: The larger of the two rules of thumb.
        adequate: Whether ``units`` reaches ``minimum_units``.
        message: One line suitable for printing above the scores.
    """

    units: int
    inputs: int
    outputs: int
    minimum_units: int
    adequate: bool
    message: str


def discrimination_check(units: int, inputs: int, outputs: int) -> DiscriminationCheck:
    """Apply the two standard rules of thumb before trusting any efficiency score.

    Args:
        units: Number of units being compared.
        inputs: Number of input measures.
        outputs: Number of output measures.

    Returns:
        A :class:`DiscriminationCheck`.

    Raises:
        ValueError: If any count is not positive.
    """
    if min(units, inputs, outputs) < 1:
        raise ValueError("units, inputs and outputs must all be at least 1")

    minimum = max(3 * (inputs + outputs), inputs * outputs)
    adequate = units >= minimum
    if adequate:
        message = (
            f"{units} units for {inputs} inputs and {outputs} outputs clears the minimum of "
            f"{minimum}; the scores can discriminate."
        )
    else:
        message = (
            f"{units} units for {inputs} inputs and {outputs} outputs is below the minimum of "
            f"{minimum}. Expect weak discrimination - a large share of units on the "
            "frontier - and expect the returns-to-scale choice to move individual scores by "
            "more than any real difference between units. Raise the number of units - "
            "site-months instead of sites - or drop measures."
        )
    return DiscriminationCheck(units, inputs, outputs, minimum, adequate, message)


def dea(
    frame: pd.DataFrame,
    inputs: Sequence[str],
    outputs: Sequence[str],
    unit: str = "site",
    returns_to_scale: str = "crs",
) -> pd.DataFrame:
    """Input-oriented DEA efficiency, solved as one linear programme per unit.

    Args:
        frame: One row per unit, with every input and output strictly positive.
        inputs: Input columns - resources consumed.
        outputs: Output columns - results produced.
        unit: Column identifying the unit.
        returns_to_scale: ``"crs"`` for constant returns (the CCR model) or ``"vrs"`` for
            variable returns (BCC). CRS charges a unit for being the wrong size; VRS does not,
            and on a network of deliberately different site sizes VRS is usually the honest
            choice. Reporting only one of them hides which effect you are measuring.

    Returns:
        One row per unit with ``efficiency`` (1.0 is on the frontier), ``slack_share`` (how far
        below one), ``peers`` (the efficient units it is compared against) and ``n_peers``.

    Raises:
        KeyError: If a column is missing.
        ValueError: If a value is not positive, or the model is unrecognised.
    """
    if returns_to_scale not in {"crs", "vrs"}:
        raise ValueError("returns_to_scale must be 'crs' or 'vrs'")
    for column in [*inputs, *outputs, unit]:
        if column not in frame.columns:
            raise KeyError(f"frame has no column {column!r}")

    input_matrix = frame[list(inputs)].to_numpy(dtype=float)
    output_matrix = frame[list(outputs)].to_numpy(dtype=float)
    if (input_matrix <= 0).any() or (output_matrix <= 0).any():
        raise ValueError("DEA requires every input and output to be strictly positive")

    names = frame[unit].astype(str).to_numpy()
    n_units = len(frame)
    rows: list[dict[str, object]] = []

    for target in range(n_units):
        solver = pywraplp.Solver.CreateSolver("GLOP")
        if solver is None:  # pragma: no cover - depends on the OR-Tools build
            raise RuntimeError("no linear solver available")

        theta = solver.NumVar(0.0, 1.0, "theta")
        lambdas = [solver.NumVar(0.0, solver.infinity(), f"lambda_{j}") for j in range(n_units)]

        # Inputs: the composite peer must use no more than theta times the target's inputs.
        for i in range(len(inputs)):
            constraint = solver.Constraint(-solver.infinity(), 0.0)
            constraint.SetCoefficient(theta, -float(input_matrix[target, i]))
            for j in range(n_units):
                constraint.SetCoefficient(lambdas[j], float(input_matrix[j, i]))

        # Outputs: the composite peer must produce at least what the target produces.
        for r in range(len(outputs)):
            constraint = solver.Constraint(float(output_matrix[target, r]), solver.infinity())
            for j in range(n_units):
                constraint.SetCoefficient(lambdas[j], float(output_matrix[j, r]))

        if returns_to_scale == "vrs":
            convexity = solver.Constraint(1.0, 1.0)
            for j in range(n_units):
                convexity.SetCoefficient(lambdas[j], 1.0)

        solver.Minimize(theta)
        if solver.Solve() != pywraplp.Solver.OPTIMAL:  # pragma: no cover - degenerate input
            rows.append({unit: names[target], "efficiency": np.nan, "peers": "", "n_peers": 0})
            continue

        efficiency = float(theta.solution_value())
        peers = [names[j] for j in range(n_units) if lambdas[j].solution_value() > TOLERANCE]
        rows.append(
            {
                unit: names[target],
                "efficiency": efficiency,
                "peers": ", ".join(peers),
                "n_peers": len(peers),
            }
        )

    result = pd.DataFrame(rows)
    result["slack_share"] = 1.0 - result["efficiency"]
    result["on_frontier"] = result["efficiency"] >= 1.0 - TOLERANCE
    return result.sort_values("efficiency", ascending=False, ignore_index=True)
