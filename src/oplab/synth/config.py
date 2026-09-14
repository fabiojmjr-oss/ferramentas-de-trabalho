"""Configuration for the synthetic data generator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class SiteProfile:
    """Operating profile of a single distribution centre.

    Attributes:
        code: Site identifier used across every generated table.
        demand_scale: Multiplier applied to base SKU demand. Sets the relative size of the site.
        promised_lead_days: Delivery lead time committed to the customer, in calendar days.
        transit_median_h: Median transit time from dispatch to delivery, in hours.
        transit_sigma: Log-scale dispersion of transit time. Higher means a fatter right tail.
        availability: Probability that an order line is shipped complete on the first attempt.
        putaway_median_h: Median dock-to-stock time on inbound, in hours.
        count_accuracy: Probability that a cycle-counted location matches the system record.
    """

    code: str
    demand_scale: float
    promised_lead_days: int
    transit_median_h: float
    transit_sigma: float
    availability: float
    putaway_median_h: float
    count_accuracy: float


DEFAULT_SITES: tuple[SiteProfile, ...] = (
    SiteProfile("CD-SP", 1.00, 1, 14.0, 0.35, 0.965, 5.0, 0.985),
    SiteProfile("CD-RJ", 0.55, 2, 26.0, 0.45, 0.940, 8.0, 0.965),
    SiteProfile("CD-PE", 0.30, 3, 52.0, 0.60, 0.905, 13.0, 0.930),
    SiteProfile("CD-RS", 0.35, 3, 44.0, 0.50, 0.925, 10.0, 0.950),
)


@dataclass(frozen=True)
class SynthConfig:
    """Parameters of a synthetic dataset.

    The defaults describe a mid-sized multi-site distribution network over one year:
    roughly 400 SKUs with a long-tailed demand profile, four sites of deliberately
    different maturity, and a horizon that ends mid-flight so that some orders are still
    in transit. That censoring is intentional - it is the most common source of inflated
    service indicators in production reporting.

    ``erratic_share`` governs a property that is easy to get wrong and changes what a
    classification can see. Demand volatility must be **decoupled from demand volume**: real
    assortments contain high-revenue items with lumpy, promotion- or project-driven demand. If
    volatility is tied to the slow-moving tail, every erratic item is low value by construction,
    an ABC-XYZ analysis can never produce an AZ cell, and the single most useful finding of that
    analysis - material revenue riding on unforecastable demand - becomes impossible to observe.
    """

    seed: int = 42
    start: date = date(2025, 1, 1)
    days: int = 365
    n_skus: int = 400
    sites: tuple[SiteProfile, ...] = DEFAULT_SITES
    intermittent_share: float = 0.35
    erratic_share: float = 0.18
    promo_rate: float = 0.02
    cancel_rate: float = 0.012
    lines_per_order: float = 3.2
    aisles: int = 20
    bays_per_aisle: int = 30
    levels: int = 4
    categories: tuple[str, ...] = field(
        default=("dry_goods", "beverages", "personal_care", "home_care", "electronics")
    )

    def __post_init__(self) -> None:
        if self.days < 28:
            raise ValueError("days must be at least 28 so that weekly seasonality is observable")
        if self.n_skus < 1:
            raise ValueError("n_skus must be positive")
        if not self.sites:
            raise ValueError("at least one site profile is required")
        if not 0.0 <= self.intermittent_share <= 1.0:
            raise ValueError("intermittent_share must be a probability")
        if not 0.0 <= self.erratic_share <= 1.0:
            raise ValueError("erratic_share must be a probability")
        if min(self.aisles, self.bays_per_aisle, self.levels) < 1:
            raise ValueError("the layout needs at least one aisle, bay and level")
        if self.pick_locations < self.n_skus:
            raise ValueError(
                f"the layout has {self.pick_locations} pick locations for {self.n_skus} SKUs; "
                "this model stores each SKU in exactly one location"
            )

    @property
    def pick_locations(self) -> int:
        """Total pick faces in the modelled layout."""
        return self.aisles * self.bays_per_aisle * self.levels

    @property
    def site_codes(self) -> tuple[str, ...]:
        return tuple(s.code for s in self.sites)

    def site(self, code: str) -> SiteProfile:
        for s in self.sites:
            if s.code == code:
                return s
        raise KeyError(code)
