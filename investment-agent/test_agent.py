"""Pruebas con CoinGecko simulado: no necesitan red."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

import agent
import indicators as ind
from market import BASE_URL, Market, MarketError

# 60 días subiendo y 30 cayendo con fuerza: deja el RSI en sobreventa.
FALLING = [100 + i for i in range(60)] + [160 - 3 * i for i in range(1, 31)]
RISING = [50 + i * 0.5 for i in range(90)]
HISTORY = {"bitcoin": RISING, "ethereum": FALLING}


def handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path.removeprefix("/api/v3")
    if path == "/simple/price":
        ids = request.url.params["ids"].split(",")
        return httpx.Response(
            200,
            json={
                i: {"usd": HISTORY[i][-1], "usd_24h_change": 1.5, "usd_market_cap": 1e9}
                for i in ids
                if i in HISTORY
            },
        )
    if path.endswith("/market_chart"):
        asset_id = path.split("/")[2]
        if asset_id not in HISTORY:
            return httpx.Response(404, json={"error": "coin not found"})
        return httpx.Response(
            200, json={"prices": [[n, p] for n, p in enumerate(HISTORY[asset_id])]}
        )
    return httpx.Response(404)


@pytest.fixture
def market(tmp_path, monkeypatch):
    portfolio = {
        "cash_usd": 0,
        "holdings": [
            {"id": "bitcoin", "amount": 10, "avg_cost_usd": 50},
            {"id": "ethereum", "amount": 1},
        ],
        "watchlist": ["ethereum", "desconocida"],
    }
    path = tmp_path / "portfolio.json"
    path.write_text(json.dumps(portfolio))
    monkeypatch.setenv("PORTFOLIO_FILE", str(path))
    client = httpx.AsyncClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    return Market(client)


def run(coro):
    return asyncio.run(coro)


def test_indicators():
    assert ind.sma([1, 2, 3, 4], 2) == 3.5
    assert ind.sma([1], 2) is None
    assert ind.rsi(list(range(1, 40))) == 100.0
    assert ind.rsi(list(range(40, 1, -1))) == 0.0
    assert ind.max_drawdown([100, 120, 60, 90]) == pytest.approx(-0.5)
    assert ind.change([100, 110, 121], 2) == pytest.approx(0.21)


def test_portfolio_values_and_weights(market):
    p = run(agent.get_portfolio(market))
    btc, eth = RISING[-1], FALLING[-1]
    assert p["total_value_usd"] == pytest.approx(10 * btc + eth)
    top = p["positions"][0]
    assert top["id"] == "bitcoin"
    assert top["pnl_usd"] == pytest.approx(10 * btc - 500)
    assert sum(x["weight_pct"] for x in p["positions"]) == pytest.approx(100, abs=0.02)
    assert "pnl_usd" not in p["positions"][1]


def test_analyze_trend(market):
    assert run(agent.analyze_asset(market, "bitcoin"))["trend"] == "alcista"
    falling = run(agent.analyze_asset(market, "ethereum"))
    assert falling["trend"] == "bajista"
    assert falling["rsi14"] < 30
    assert falling["max_drawdown_pct"] == pytest.approx((70 / 159 - 1) * 100, abs=0.01)


def test_risk_flags_concentration(market):
    risk = run(agent.calculate_risk(market))
    assert any("bitcoin" in w for w in risk["warnings"])
    assert any("efectivo" in w for w in risk["warnings"])
    assert 0 < risk["concentration_hhi"] <= 1
    assert risk["daily_var_95_usd"] > 0


def test_opportunities_and_unknown_asset(market):
    result = run(agent.find_opportunities(market))
    reasons = [s["reason"] for s in result["signals"] if s["id"] == "ethereum"]
    assert any("sobreventa" in r for r in reasons)
    assert any("7 días" in r for r in reasons)
    assert [e["id"] for e in result["errors"]] == ["desconocida"]
    # bitcoin sube sin pausa: RSI 100 y está en cartera.
    assert any(
        s["id"] == "bitcoin" and s["type"] == "posible toma de ganancias"
        for s in result["signals"]
    )


def test_trade_plan_respects_risk(market):
    plan = run(agent.generate_trade_plan(market, "ethereum", 1000, 2))
    assert plan["stop_loss_usd"] < plan["entry_usd"] < plan["targets_usd"]["1.5R"]
    assert plan["max_loss_usd"] <= 20.01
    assert plan["position_size_usd"] <= 1000
    with pytest.raises(MarketError):
        run(agent.generate_trade_plan(market, "ethereum", 0))


def test_alert_without_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    with pytest.raises(MarketError):
        run(agent.send_alert("hola"))
