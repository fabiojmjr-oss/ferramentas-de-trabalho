# oplab — operations analytics toolkit

[![ci](https://github.com/fabiojmjr-oss/ferramentas-de-trabalho/actions/workflows/ci.yml/badge.svg)](https://github.com/fabiojmjr-oss/ferramentas-de-trabalho/actions/workflows/ci.yml)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

Logistics indicators, statistical process control, and the synthetic supply chain data to
exercise both. Python, tested, typed.

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

## What is in it

| Module | The question it answers | Status |
| --- | --- | --- |
| `oplab.synth` | What data do I test against without exposing a real operation? | Available |
| `oplab.kpi` | What is the service level, and how much of it is definition? | Available |
| `oplab.spc` | Did the process change, and is it capable of the specification? | Available |

Full build sequence in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Install

```bash
git clone https://github.com/fabiojmjr-oss/ferramentas-de-trabalho.git
cd ferramentas-de-trabalho
pip install -e ".[dev]"
pytest
```

## Thirty seconds

```python
from oplab.kpi import service_sensitivity
from oplab.synth import generate_dataset

dataset = generate_dataset()  # reproducible from the seed alone
print(service_sensitivity(dataset.order_lines))  # one order book, four conventions
```

---

## Three things it demonstrates

### 1. A sixteen-point service spread with no change to the operation

`examples/01_service_definition.py` measures one order book — 300,718 lines over a year across
four sites — under four reporting conventions:

| Convention | OTIF | On time | In full | Lines in scope |
| --- | --- | --- | --- | --- |
| Undelivered lines counted as failures | 76.1% | 78.6% | 92.6% | 296,962 |
| Undelivered lines excluded *(default)* | 79.4% | 82.1% | 96.7% | 284,412 |
| One day of grace on the promise | 91.6% | 94.7% | 96.7% | 284,412 |
| Grace plus a 5% quantity tolerance | 91.7% | 94.7% | 96.7% | 284,412 |

Nothing about the operation differs between those rows. The 15.6-point spread is definition,
and it is usually wider than the improvement being negotiated in the room.

It also reorders the network. CD-SP is second on the strict convention and first once a day of
grace is allowed; CD-RJ goes the other way. A target set before the definition is settled is
not a target.

And on the same data, fill rate is 98.4% per unit, 96.7% per line, and 90.0% per order. All
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
| Centre line | 499.95 | 500.91 |
| Limit half-width | 2.764 | 2.676 |
| Signals in the stable phase | 1 | 12 |

The half-width barely moves. The **centre line** is dragged towards the disturbed period, which
manufactures twelve signals in a period that was stable and dates the change wrongly — and a
wrong date sends the investigation to the wrong shift, the wrong batch and the wrong cause.

Limits do inflate when sigma is estimated from the standard deviation of the plotted points
instead of within-subgroup variation. That is a different error, and no function here commits
it.

### 3. A quarter of all signals produced by the wrong unit of analysis

A p chart of late deliveries at one site, same period, same chart type, differing only in what
counts as one trial:

| Unit of analysis | n per day | Days signalled | Overdispersion |
| --- | --- | --- | --- |
| Order line | 91–300 | 98 of 359 | 2.12 |
| Order | 30–93 | 7 of 359 | 1.01 |

Every line of an order rides the same vehicle, so one late truck produces a dozen correlated
failures. The binomial model behind the p chart assumes independent trials, observed variation
comes out at 2.12× what it predicts, and 27% of days signal — every one of them an artefact.
At order level the ratio is 1.01 and the signal rate falls to the expected false-alarm rate.

`oplab.spc.overdispersion_ratio` reports this, and it is worth checking before any signal is
investigated.

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

**Test against hand calculations.** Control chart limits are checked against `A2`, `D3` and
`D4` from the published tables on subgroups whose ranges are exact by construction. Service
metrics are checked against a six-line fixture whose expected values were derived by hand. A
metric tested only against its own implementation tests nothing.

**No real data, ever.** Every table comes from `oplab.synth` with a fixed seed. See
[`DISCLAIMER.md`](DISCLAIMER.md).

## Limitations

Stated plainly, because the gaps matter as much as the coverage:

- The synthetic generator produces **plausible** data, not calibrated data. It is built to
  exercise the analytics and to make examples reproducible. No figure in this repository should
  be read as the performance of any real operation.
- Capability indices assume approximate normality. `oplab.spc.capability` reports skewness and
  kurtosis and warns when the assumption is doubtful, but it does not implement
  non-normal capability methods. Logistics durations are usually right skewed, so this matters
  more here than in manufacturing.
- There is no forecasting, optimisation or simulation yet. Those are waves 2 to 4 of
  [`docs/ROADMAP.md`](docs/ROADMAP.md).
- Attribute charts assume independent trials. `overdispersion_ratio` detects the violation but
  the library does not yet offer a Laney p′ chart or another overdispersion-robust alternative.

## Development

```bash
ruff check . && ruff format --check .   # lint and format
mypy                                    # type check
pytest --cov                            # 131 tests, 94% statement coverage
```

CI runs all four on Python 3.10 and 3.12.

## License

MIT. See [`LICENSE`](LICENSE).
