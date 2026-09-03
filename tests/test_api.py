from datetime import date

import pytest
from conftest import StubStrategy, bars

fastapi = pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from ai_stock_trader.adapters.store.sqlite import SqliteStore  # noqa: E402
from ai_stock_trader.api.app import create_app  # noqa: E402
from ai_stock_trader.app.daily import run_daily  # noqa: E402
from ai_stock_trader.domain.models import BUY, HOLD  # noqa: E402
from ai_stock_trader.domain.risk import RiskConfig  # noqa: E402


@pytest.fixture()
def seeded_db(tmp_path):
    path = tmp_path / "trader.db"
    with SqliteStore(path, "default") as store:
        run_daily(
            store,
            bars([100, 100, 110, 108, 112], "TEST"),
            StubStrategy([BUY, HOLD, HOLD, HOLD, HOLD]),
            initial_cash=100_000,
            risk_config=RiskConfig(max_position_weight=0.5),
        )
    return path


@pytest.fixture()
def client(seeded_db):
    return TestClient(create_app(str(seeded_db), "default"))


def test_dashboard_serves_html(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "AI Stock Trader" in response.text


def test_accounts_lists_the_seeded_account(client):
    assert client.get("/api/accounts").json() == ["default"]


def test_accounts_falls_back_to_the_default_when_the_file_is_empty(tmp_path):
    empty_client = TestClient(create_app(str(tmp_path / "empty.db"), "solo"))
    assert empty_client.get("/api/accounts").json() == ["solo"]


def test_status_reports_cash_equity_and_positions(client):
    body = client.get("/api/status", params={"account": "default"}).json()
    assert body["exists"] is True
    assert body["positions"][0]["symbol"] == "TEST"
    assert body["metrics"]["trade_count"] == 1


def test_status_for_an_unknown_account_is_empty_not_a_404(client):
    body = client.get("/api/status", params={"account": "nobody"}).json()
    assert body["exists"] is False


def test_equity_curve_has_one_point_per_processed_date(client):
    curve = client.get("/api/equity-curve", params={"account": "default"}).json()
    assert len(curve) == 4  # 5 bars, 4 executable dates
    assert curve[0]["date"] == "2025-01-02"


def test_trades_lists_the_executed_buy(client):
    trades = client.get("/api/trades", params={"account": "default"}).json()
    assert [t["action"] for t in trades] == ["BUY"]


def test_a_pending_proposal_can_be_approved(client):
    status = client.get("/api/status", params={"account": "default"}).json()
    proposal = status["pending_proposals"][0]
    response = client.post(
        "/api/proposals/decide",
        json={
            "account": "default",
            "date": proposal["date"],
            "symbol": proposal["symbol"],
            "status": "APPROVED",
            "note": "確認済み",
        },
    )
    assert response.status_code == 200
    refreshed = client.get("/api/status", params={"account": "default"}).json()
    approved = next(p for p in refreshed["pending_proposals"] if p["symbol"] == proposal["symbol"])
    assert (approved["status"], approved["note"]) == ("APPROVED", "確認済み")


def test_deciding_an_unknown_proposal_returns_404(client):
    response = client.post(
        "/api/proposals/decide",
        json={"account": "default", "date": "2020-01-01", "symbol": "TEST", "status": "APPROVED"},
    )
    assert response.status_code == 404


def test_an_invalid_date_returns_400(client):
    response = client.post(
        "/api/proposals/decide",
        json={"account": "default", "date": "not-a-date", "symbol": "TEST", "status": "APPROVED"},
    )
    assert response.status_code == 400


def test_an_invalid_status_is_rejected_by_request_validation(client):
    response = client.post(
        "/api/proposals/decide",
        json={"account": "default", "date": "2025-01-06", "symbol": "TEST", "status": "MAYBE"},
    )
    assert response.status_code == 422


def test_accounts_are_isolated_through_the_api(seeded_db):
    with SqliteStore(seeded_db, "second") as store:
        run_daily(
            store,
            bars([50, 50, 55], "OTHER"),
            StubStrategy([HOLD, HOLD, HOLD]),
            initial_cash=50_000,
        )
    client = TestClient(create_app(str(seeded_db), "default"))
    accounts = client.get("/api/accounts").json()
    assert set(accounts) == {"default", "second"}
    second_status = client.get("/api/status", params={"account": "second"}).json()
    assert second_status["cash"] == 50_000
