# oplab — operations analytics toolkit

[![ci](https://github.com/fabiojmjr-oss/ferramentas-de-trabalho/actions/workflows/ci.yml/badge.svg)](https://github.com/fabiojmjr-oss/ferramentas-de-trabalho/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

Logistics indicators, statistical process control, pick-face slotting, cost variance
decomposition, discrete-event capacity simulation, and the synthetic supply chain data to
exercise all of it. Python, tested, typed.

**[Leia em português →](README.pt-BR.md)**

---

## Why this exists

Most operational reporting problems are not calculation problems. The arithmetic behind OTIF,
fill rate and inventory accuracy is trivial; what decides whether the number is right is a set
of conventions that are almost never written down — whether the promise is an instant or a
date, whether a cancelled line belongs in the denominator, whether accuracy counts locations
or units.

This repository takes the position that those conventions belong in code, with tests, where
they can be argued about and audited. Each function exposes its choices as arguments, and where
a metric has more than one legitimate definition it returns all of them rather than picking
one silently.

## Modules

| Module | The question it answers | Docs |
| --- | --- | --- |
| `oplab.synth` | What data do I test against without exposing a real operation? | [`DISCLAIMER.md`](DISCLAIMER.md) |
| `oplab.kpi` | What is the service level, and how much of it is definition? | — |
| `oplab.spc` | Did the process change, and is it capable of the specification? | — |
| `oplab.slotting` | Which items deserve which policy, and what does the layout cost? | [README](src/oplab/slotting/README.md) |
| `oplab.variance` | Why did cost per order move, and who owns each part of it? | [README](src/oplab/variance/README.md) |
| `oplab.simulation` | Where is the constraint, and what does relieving it buy? | [README](src/oplab/simulation/README.md) |

Four more tools are planned. Build sequence and selection rule in
[`docs/ROADMAP.md`](docs/ROADMAP.md).

## Install

```bash
git clone https://github.com/fabiojmjr-oss/ferramentas-de-trabalho.git
cd ferramentas-de-trabalho
make install
make check
```

## Thirty seconds

```python
from oplab.kpi import service_sensitivity
from oplab.synth import generate_dataset

dataset = generate_dataset()  # reproducible from the seed alone
print(service_sensitivity(dataset.order_lines))  # one order book, four conventions
```

---

## Six things it demonstrates

### 1. A sixteen-point service spread with no change to the operation

`examples/01_service_definition.py` measures one order book — 290,918 lines over a year across
four sites — under four reporting conventions:

| Convention | OTIF | On time | In full | Lines in scope |
| --- | --- | --- | --- | --- |
| Undelivered lines counted as failures | 76.0% | 78.5% | 92.6% | 287,352 |
| Undelivered lines excluded *(default)* | 79.4% | 82.0% | 96.7% | 275,163 |
| One day of grace on the promise | 91.5% | 94.6% | 96.7% | 275,163 |
| Grace plus a 5% quantity tolerance | 91.6% | 94.6% | 96.7% | 275,163 |

Nothing about the operation differs between those rows. The 15.6-point spread is definition,
and it is usually wider than the improvement being negotiated in the room.

It also reorders the network. CD-SP is second on the strict convention and first once a day of
grace is allowed; CD-RJ goes the other way. A target set before the definition is settled is
not a target.

And on the same data, fill rate is 98.3% per unit, 96.7% per line, and 90.0% per order. All
three are correct. Quoting one without naming the basis is how two functions report different
service levels from the same extract and neither is wrong.

### 2. Control limits are not the thing a contaminated baseline breaks

It is widely repeated that fitting control limits to a period containing the disturbance
inflates them until the disturbance sits inside. On an X-bar and R chart that is false, and the
reason matters: the limit half-width is `A2 × R̄`, built from **within-subgroup** range, and a
shift in the process mean between subgroups leaves that range untouched.

Measured on a series with a 1.6σ shift injected at subgroup 43:

| | Limits from the stable phase | Limits from the whole series |
| --- | --- | --- |
| Centre line | 499.72 | 500.67 |
| Limit half-width | 2.930 | 2.728 |
| Signals in the stable phase | 0 | 14 |

The centre line moves by nearly five times as much as the half-width does, and it is dragged
towards the disturbed period — which manufactures fourteen signals in a period that was stable
and dates the change wrongly. A wrong date sends the investigation to the wrong shift, the
wrong batch and the wrong cause.

Limits do inflate when sigma is estimated from the standard deviation of the plotted points
instead of within-subgroup variation. That is a different error, and no function here commits
it.

### 3. A quarter of all signals produced by the wrong unit of analysis

A p chart of late deliveries at one site, same period, same chart type, differing only in what
counts as one trial:

| Unit of analysis | n per day | Days signalled | Overdispersion |
| --- | --- | --- | --- |
| Order line | 80–295 | 95 of 359 | 2.12 |
| Order | 25–89 | 4 of 359 | 1.01 |

Every line of an order rides the same vehicle, so one late truck produces a dozen correlated
failures. The binomial model behind the p chart assumes independent trials, observed variation
comes out at 2.12× what it predicts, and 26% of days signal — every one of them an artefact.
At order level the ratio is 1.01 and the signal rate falls to the expected false-alarm rate.

`oplab.spc.overdispersion_ratio` reports this, and it is worth checking before any signal is
investigated.

### 4. In slotting, the algorithm is a rounding error

Three ranking rules against the current random placement of 400 SKUs over 2,400 pick faces:

| Strategy | Mean distance per pick | Change |
| --- | --- | --- |
| By popularity (picks) | 17.11 m | −67.2% |
| By revenue | 17.34 m | −66.7% |
| By cube-per-order index | 18.00 m | −65.5% |
| Current (as received) | 52.11 m | — |

Every rule recovers about two thirds of the travel, and the spread between the best and the
worst rule is 1.7 points. **The decision worth money is whether to re-slot at all; the choice of
algorithm is a rounding error next to it** — the opposite of how slotting software is sold.

The cube-per-order index coming last is correct rather than a defect: with one face per SKU and
uniform capacity, every item consumes the same space, so cube carries no information about the
objective. Details, and the condition under which COI does win, in the
[module README](src/oplab/slotting/README.md).

The classification behind it earns its own finding: 18 of 87 class A items are not stable, and
they carry 19.1% of class A value. An ABC-only exercise hands all of them the policy designed
for predictable demand, and that is where the service failures come from.

### 5. The same cost movement, attributed two different ways

Cost per order rose 20.7% over the year on the bundled ledger. The decomposition is exact
either way, and the segmentation decides the answer:

| Effect | Segmented by site and order size | With channel added |
| --- | --- | --- |
| Rate | **+15.61 (99.1%)** | +11.67 (74.1%) |
| Mix | +0.14 (0.9%) | **+4.08 (25.9%)** |
| Total | +15.75 | +15.75 |

The movement is identical. The attribution is not. Omit the channel dimension and 99% of the
rise reads as operational; add it and a quarter is mix, because the direct-to-consumer share
grew and a home delivery costs nearly twice as much per stop as a store delivery.

**An omitted dimension does not disappear. It reappears inside the rate effect and is
attributed to whoever owns the rate** — and it is invisible, because the arithmetic reconciles
to 2.8e-14 either way.

Two more things fall out of the same module. Total cost rose 28.1%, of which 22% was volume —
the same business got bigger, which is not a cost problem. And a per-unit metric cannot move
through volume at all: the bridge has exactly two terms by construction, so *"cost per order
rose but volume grew"* is not an explanation. Details, including the operating-leverage caveat
that qualifies it, in the [module README](src/oplab/variance/README.md).

### 6. The capacity spreadsheet is right, and still points at the wrong decision

Utilisation is conserved, so dividing mean work by mean capacity computes it correctly. The
simulated figures match the spreadsheet to within a point. And they decide nothing:

| Resource | Utilisation | Total waiting caused |
| --- | --- | --- |
| Picking (18 people) | 77.9% | **26,425 h** |
| Checking (5 stations) | 95.3% | 9,622 h |

**Utilisation ranks nothing.** Picking sits at a comfortable load and causes nearly three times
the waiting of the resource at 95%, because orders are released in two waves and every order
queues behind half a day's work the moment it arrives. That is a release policy, not a capacity
shortfall, and no utilisation figure separates the two.

What that does to the investment case, over six replications at 95% confidence:

| Scenario | Cycle time | Change | Distinguishable |
| --- | --- | --- | --- |
| **Release in 8 waves instead of 2** | 0.82 h | **−61.7%** | Yes |
| +2 checking stations | 1.68 h | −22.0% | Yes |
| Shift 8 h to 10 h | 2.02 h | −6.1% | Yes |
| +2 inbound doors | 2.15 h | 0.0% | **No** |
| +4 pickers | 2.17 h | +0.7% | **No** |

The free operational change recovers 2.8 times what the best paid option does. And four more
pickers — the intuitive move, aimed at the longest queue and the largest team — **cannot be
shown to do anything**: its interval overlaps the base, and it moved the wrong way. Without the
interval, that point estimate would have been reported as a result.

Details, including why an inbound investment provably cannot move an outbound metric in this
model, in the [module README](src/oplab/simulation/README.md).

---

## Design principles

**Validate at the boundary.** Every public KPI function checks its input against a contract in
`oplab.kpi.schemas` and reports every problem in one pass. A service number computed on a
malformed extract is worse than no number, because it is reported with the same confidence as
a correct one.

**Quantify the trade-off instead of asserting it.** The false-alarm rates of the Nelson rule
sets — 1 in 420 points for rule 1 alone, 1 in 70 for the practical set, 1 in 42 for all eight
— are measured in `tests/spc/test_rules.py::test_false_alarm_rates`, not quoted from memory.

**Return every legitimate definition.** Three fill rate bases, three inventory accuracy
definitions, Cpk beside Ppk. The gap between them is usually the finding.

**Report the result that contradicts the pitch.** The cube-per-order index loses to plain
popularity here, and the module says so and explains why, rather than quietly dropping the
comparison.

**Reconcile exactly or fail.** Variance effects sum to the movement with no residual, and
`waterfall()` raises rather than draw bars that miss the closing total. A decomposition with a
plug line is an allocation with a plug line, and the plug is where disagreements hide.

**Never report a stochastic point estimate as an answer.** Simulation results carry confidence
intervals, and a scenario whose interval overlaps the base is reported as indistinguishable
rather than as a small improvement.

**Test against hand calculations.** Control chart limits are checked against `A2`, `D3` and
`D4` from the published tables on subgroups whose ranges are exact by construction. Service
metrics are checked against a six-line fixture whose expected values were derived by hand. A
metric tested only against its own implementation tests nothing.

**No real data, ever.** Every table comes from `oplab.synth` with a fixed seed. See
[`DISCLAIMER.md`](DISCLAIMER.md).

**The README is under test.** Every figure quoted above is asserted in
`tests/test_readme_claims.py`, and the example scripts are executed there too. Any change that
moves one of these numbers breaks the build rather than leaving the text quietly wrong.

## Limitations

Stated plainly, because the gaps matter as much as the coverage:

- The synthetic generator produces **plausible** data, not calibrated data. It is built to
  exercise the analytics and to make examples reproducible. No figure in this repository should
  be read as the performance of any real operation.
- Capability indices assume approximate normality. `oplab.spc.capability` reports skewness and
  kurtosis and warns when the assumption is doubtful, but it does not implement non-normal
  capability methods. Logistics durations are usually right skewed, so this matters more here
  than in manufacturing.
- Slotting measures distance-weighted picks, not routes, and assumes one location per SKU with
  no congestion and no move cost. Every one of those assumptions overstates the benefit; see
  the [module README](src/oplab/slotting/README.md) for the full list and for why the
  percentage change is quotable and the metres are not.
- Attribute charts assume independent trials. `overdispersion_ratio` detects the violation but
  the library does not yet offer a Laney p′ chart or another overdispersion-robust alternative.
- Variance decomposition is only as good as its segmentation — mix is invisible along a
  dimension you do not segment by — and it does not split fixed from variable cost, so
  operating leverage hides inside the rate effect. It also compares two periods with no test of
  whether the movement exceeds normal variation; chart it with `oplab.spc` first.
- The capacity simulation keeps inbound and outbound labour in separate pools, holds a resource
  across the shift break, and leaves loading, replenishment and travel distance out of scope.
  See the [module README](src/oplab/simulation/README.md); the first assumption in particular
  understates the value of cross-deploying people.
- There is no forecasting or route optimisation yet. Those are waves 3 and 4 of
  [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Development

```bash
make install   # editable install with the dev tools
make check     # lint, format check, type check, test - exactly what CI runs
make examples  # run all five example scripts
```

`make check` exists because the alternative failed twice: running the linter but forgetting the
formatter, and running a locally installed tool older than the one CI installs. Both turned a
correct change into a red build, so the linters are pinned to a compatible release and the
whole sequence lives in one target. CI runs the same four checks on Python 3.10 and 3.12.

273 tests, 95% statement coverage. The suite takes about two minutes, most of it spent
verifying the simulation figures quoted above - which is the cost of having them under test.

## License

MIT. See [`LICENSE`](LICENSE).
