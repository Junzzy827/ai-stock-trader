"""TOML configuration.

Once a run covers several symbols, passing every parameter on the command line
stops being practical and, more importantly, stops being reproducible: the
config file is the record of what a stored account was actually run with.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from .domain.market import JAPAN, MarketSpec
from .domain.risk import RiskConfig
from .domain.strategy import StrategyConfig

SECTIONS = ("account", "data", "market", "strategy", "risk")


@dataclass(frozen=True)
class AppConfig:
    account: str = "default"
    capital: float = 1_000_000
    database: str = "trader.db"
    csv: str | None = None
    symbols: tuple[str, ...] = ()
    rss: tuple[str, ...] = ()
    slippage_rate: float = 0.0
    market: MarketSpec = JAPAN
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)

    def with_overrides(self, **overrides: Any) -> "AppConfig":
        """Apply command-line values, ignoring the ones left unset."""
        supplied = {key: value for key, value in overrides.items() if value is not None}
        market_keys = {"lot_size", "commission_rate", "min_commission"}
        risk_keys = {
            "max_position_weight",
            "cash_buffer",
            "stop_loss_pct",
            "trailing_stop_pct",
            "max_positions",
        }
        market = replace(self.market, **{k: v for k, v in supplied.items() if k in market_keys})
        risk = replace(self.risk, **{k: v for k, v in supplied.items() if k in risk_keys})
        top_level = {
            key: value
            for key, value in supplied.items()
            if key not in market_keys and key not in risk_keys
        }
        if "symbols" in top_level:
            top_level["symbols"] = tuple(top_level["symbols"])
        if "rss" in top_level:
            top_level["rss"] = tuple(top_level["rss"])
        return replace(self, market=market, risk=risk, **top_level)


def load_config(path: str | Path) -> AppConfig:
    file = Path(path)
    if not file.exists():
        raise FileNotFoundError(f"config not found: {file}")
    with file.open("rb") as handle:
        raw = tomllib.load(handle)
    unknown = set(raw) - set(SECTIONS)
    if unknown:
        raise ValueError(f"unknown config sections: {', '.join(sorted(unknown))}")

    account = _section(raw, "account")
    data = _section(raw, "data")
    return AppConfig(
        account=account.get("name", "default"),
        capital=float(account.get("capital", 1_000_000)),
        database=account.get("database", "trader.db"),
        csv=data.get("csv"),
        symbols=tuple(data.get("symbols", ())),
        rss=tuple(data.get("rss", ())),
        slippage_rate=float(_section(raw, "market").pop("slippage_rate", 0.0)),
        market=_build(MarketSpec, _section(raw, "market"), "market"),
        strategy=_build(StrategyConfig, _section(raw, "strategy"), "strategy"),
        risk=_build(RiskConfig, _section(raw, "risk"), "risk"),
    )


def _section(raw: dict[str, Any], name: str) -> dict[str, Any]:
    section = raw.get(name, {})
    if not isinstance(section, dict):
        raise ValueError(f"[{name}] must be a table")
    return dict(section)


def _build(factory: type, values: dict[str, Any], name: str) -> Any:
    values.pop("slippage_rate", None)
    allowed = set(factory.__dataclass_fields__)
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"unknown keys in [{name}]: {', '.join(sorted(unknown))}")
    return factory(**values)
