"""Comparing sites of different size and mix.

Ranking a network on a raw indicator produces a political ranking, and the room knows it. Three
steps make the comparison defensible, and the third one is where most scorecards fail:

1. :func:`scale_normalise` and :func:`indirect_standardisation` remove size and mix. The second
   is the one that answers "our mix is harder" with arithmetic instead of argument.
2. :func:`peer_z_scores` and :func:`composite_index` build a score under an explicit weighting.
3. :func:`rank_stability` measures how much of the resulting ranking is the weighting rather
   than the data.

:func:`dea` offers relative efficiency across several inputs and outputs without needing prices
for them - but call :func:`discrimination_check` first. On a small network DEA returns everybody
as efficient, and that is a property of the method, not a finding about the sites.

Requires the linear solver from OR-Tools: ``pip install -e ".[benchmark]"``.
"""

from .dea import DiscriminationCheck, dea, discrimination_check
from .normalise import indirect_standardisation, scale_normalise
from .scores import composite_index, peer_z_scores, rank_stability

__all__ = [
    "DiscriminationCheck",
    "composite_index",
    "dea",
    "discrimination_check",
    "indirect_standardisation",
    "peer_z_scores",
    "rank_stability",
    "scale_normalise",
]
