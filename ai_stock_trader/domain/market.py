"""Exchange conventions kept in one place instead of hard-coded in the engine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketSpec:
    name: str = "JP"
    currency: str = "JPY"
    lot_size: int = 100
    commission_rate: float = 0.001
    min_commission: float = 0.0

    def __post_init__(self) -> None:
        if self.lot_size < 1:
            raise ValueError("lot_size must be at least 1")
        if self.commission_rate < 0:
            raise ValueError("commission_rate must not be negative")
        if self.min_commission < 0:
            raise ValueError("min_commission must not be negative")

    def commission(self, notional: float) -> float:
        if notional <= 0:
            return 0.0
        return max(abs(notional) * self.commission_rate, self.min_commission)

    def round_to_lot(self, quantity: int) -> int:
        """Round down to a tradable quantity (100 shares for most TSE names)."""
        return (int(quantity) // self.lot_size) * self.lot_size


JAPAN = MarketSpec()
US = MarketSpec(name="US", currency="USD", lot_size=1)
