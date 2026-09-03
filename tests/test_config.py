import pytest

from ai_stock_trader.config import AppConfig, load_config

FULL = """
[account]
name = "paper1"
capital = 3000000
database = "state/paper1.db"

[data]
csv = "data/prices.csv"
symbols = ["7203", "6758"]
rss = ["https://example.com/feed.xml"]

[market]
lot_size = 100
commission_rate = 0.0005
slippage_rate = 0.001

[strategy]
short_sma = 3
long_sma = 10

[risk]
max_position_weight = 0.3
stop_loss_pct = 0.07
max_positions = 2
"""


def write(tmp_path, text: str):
    path = tmp_path / "config.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_every_section_is_loaded(tmp_path):
    config = load_config(write(tmp_path, FULL))
    assert (config.account, config.capital, config.database) == ("paper1", 3_000_000, "state/paper1.db")
    assert config.symbols == ("7203", "6758")
    assert config.rss == ("https://example.com/feed.xml",)
    assert config.market.commission_rate == 0.0005
    assert config.slippage_rate == 0.001
    assert (config.strategy.short_sma, config.strategy.long_sma) == (3, 10)
    assert (config.risk.max_position_weight, config.risk.max_positions) == (0.3, 2)


def test_omitted_sections_fall_back_to_the_defaults(tmp_path):
    config = load_config(write(tmp_path, '[data]\ncsv = "p.csv"\n'))
    assert config == AppConfig(csv="p.csv")


def test_an_unknown_section_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown config sections: broker"):
        load_config(write(tmp_path, "[broker]\nkind = 'live'\n"))


def test_an_unknown_key_names_its_section(tmp_path):
    with pytest.raises(ValueError, match=r"unknown keys in \[risk\]: leverage"):
        load_config(write(tmp_path, "[risk]\nleverage = 3\n"))


def test_an_invalid_value_is_rejected_by_the_domain_rules(tmp_path):
    with pytest.raises(ValueError, match="max_position_weight"):
        load_config(write(tmp_path, "[risk]\nmax_position_weight = 2.0\n"))


def test_a_missing_file_is_reported_clearly(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "absent.toml")


def test_command_line_values_override_the_file(tmp_path):
    config = load_config(write(tmp_path, FULL)).with_overrides(
        capital=500_000, stop_loss_pct=0.02, symbols=["9984"]
    )
    assert config.capital == 500_000
    assert config.risk.stop_loss_pct == 0.02
    assert config.symbols == ("9984",)


def test_unset_command_line_values_leave_the_file_alone(tmp_path):
    loaded = load_config(write(tmp_path, FULL))
    assert loaded.with_overrides(capital=None, stop_loss_pct=None, lot_size=None) == loaded
