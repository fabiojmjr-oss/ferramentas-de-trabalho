"""Operations analytics toolkit.

Three layers, in dependency order:

``oplab.synth``
    Seeded synthetic supply chain data. Every example in this repository is built on it,
    so results are reproducible and no real operation is exposed.
``oplab.kpi``
    Logistics service and flow indicators with explicit, testable definitions.
``oplab.spc``
    Statistical process control: control charts, Nelson run rules, capability indices.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
