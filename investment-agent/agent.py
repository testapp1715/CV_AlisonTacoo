"""Lógica del agente: portafolio, análisis, riesgo, oportunidades, plan y alertas.

No ejecuta operaciones: las compras y ventas se hacen a mano en la app.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx

import indicators as ind
from market import Market, MarketError

DEFAULT_RULES = {
    "rsi_oversold": 30,
    "rsi_overbought": 70,
    "drop_7d_pct": 15,
    "max_position_pct": 40,
}
HISTORY_DAYS = 90


def _pct(value: float | None) -> float | None:
    return None if value is None else round(value * 100, 2)


def portfolio_path() -> Path:
    return Path(
        os.environ.get("PORTFOLIO_FILE", Path(__file__).parent / "portfolio.json")
    )


def load_config() -> dict[str, Any]:
    path = portfolio_path()
    if not path.exists():
        raise MarketError(
            f"No existe {path}. Copia portfolio.example.json a portfolio.json "
            "y anota ahí tus posiciones."
        )
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MarketError(f"{path} no es JSON válido: {exc}") from exc
    config.setdefault("holdings", [])
    config.setdefault("watchlist", [])
    config.setdefault("cash_usd", 0)
    config["rules"] = {**DEFAULT_RULES, **config.get("rules", {})}
    return config


async def get_portfolio(market: Market) -> dict[str, Any]:
    config = load_config()
    holdings = config["holdings"]
    prices = await market.prices([h["id"] for h in holdings])
    positions = []
    invested = 0.0
    for holding in holdings:
        quote = prices.get(holding["id"], {})
        position: dict[str, Any] = {"id": holding["id"], "amount": holding["amount"]}
        if "error" in quote:
            position["error"] = quote["error"]
            positions.append(position)
            continue
        value = holding["amount"] * quote["price"]
        invested += value
        position.update(
            price_usd=quote["price"],
            value_usd=round(value, 2),
            change_24h_pct=quote["change_24h_pct"],
        )
        avg_cost = holding.get("avg_cost_usd")
        if avg_cost:
            cost = holding["amount"] * avg_cost
            position.update(
                avg_cost_usd=avg_cost,
                pnl_usd=round(value - cost, 2),
                pnl_pct=_pct(value / cost - 1),
            )
        positions.append(position)

    total = invested + config["cash_usd"]
    for position in positions:
        if "value_usd" in position:
            position["weight_pct"] = _pct(position["value_usd"] / total) if total else None
    return {
        "source": f"archivo local {portfolio_path().name} (se actualiza a mano)",
        "total_value_usd": round(total, 2),
        "invested_usd": round(invested, 2),
        "cash_usd": config["cash_usd"],
        "positions": sorted(
            positions, key=lambda p: p.get("value_usd", 0), reverse=True
        ),
    }


async def analyze_asset(
    market: Market, asset_id: str, days: int = HISTORY_DAYS
) -> dict[str, Any]:
    closes = await market.daily_closes(asset_id, days)
    price = closes[-1]
    sma20, sma50 = ind.sma(closes, 20), ind.sma(closes, 50)
    rsi14 = ind.rsi(closes)
    daily_vol = ind.volatility(ind.returns(closes))

    if sma20 is None or sma50 is None:
        trend = "sin datos suficientes"
    elif price > sma20 > sma50:
        trend = "alcista"
    elif price < sma20 < sma50:
        trend = "bajista"
    else:
        trend = "lateral o indefinida"

    return {
        "id": asset_id,
        "price_usd": price,
        "days_analyzed": len(closes),
        "change_7d_pct": _pct(ind.change(closes, 7)),
        "change_30d_pct": _pct(ind.change(closes, 30)),
        "sma20": sma20,
        "sma50": sma50,
        "rsi14": None if rsi14 is None else round(rsi14, 1),
        "trend": trend,
        "volatility_daily_pct": _pct(daily_vol),
        "volatility_annual_pct": _pct(ind.annualize(daily_vol)),
        "max_drawdown_pct": _pct(ind.max_drawdown(closes)),
        "period_high": max(closes),
        "period_low": min(closes),
    }


async def calculate_risk(market: Market) -> dict[str, Any]:
    config = load_config()
    portfolio = await get_portfolio(market)
    priced = [p for p in portfolio["positions"] if "value_usd" in p]
    total = portfolio["total_value_usd"]
    if not priced or not total:
        return {"error": "El portafolio no tiene posiciones con precio."}

    series: dict[str, list[float]] = {}
    per_asset = []
    for position in priced:
        closes = await market.daily_closes(position["id"], HISTORY_DAYS)
        series[position["id"]] = ind.returns(closes)
        per_asset.append(
            {
                "id": position["id"],
                "weight_pct": position["weight_pct"],
                "volatility_annual_pct": _pct(
                    ind.annualize(ind.volatility(series[position["id"]]))
                ),
                "max_drawdown_pct": _pct(ind.max_drawdown(closes)),
            }
        )

    # Retorno diario del portafolio con los pesos actuales (el efectivo no se mueve).
    length = min(len(r) for r in series.values())
    weights = {p["id"]: p["value_usd"] / total for p in priced}
    combined = [
        sum(weights[i] * series[i][len(series[i]) - length + day] for i in series)
        for day in range(length)
    ]
    daily_vol = ind.volatility(combined)
    equity = [1.0]
    for r in combined:
        equity.append(equity[-1] * (1 + r))

    warnings = []
    limit = config["rules"]["max_position_pct"]
    for position in priced:
        if position["weight_pct"] > limit:
            warnings.append(
                f"{position['id']} pesa {position['weight_pct']} % del portafolio "
                f"(límite configurado: {limit} %)."
            )
    cash_pct = _pct(portfolio["cash_usd"] / total)
    if cash_pct == 0:
        warnings.append("No hay efectivo disponible para aprovechar caídas.")

    return {
        "total_value_usd": total,
        "cash_pct": cash_pct,
        "concentration_hhi": round(sum(w * w for w in weights.values()), 3),
        "portfolio_volatility_annual_pct": _pct(ind.annualize(daily_vol)),
        "portfolio_max_drawdown_pct": _pct(ind.max_drawdown(equity)),
        # Pérdida diaria que solo se supera ~1 de cada 20 días, asumiendo normalidad.
        "daily_var_95_usd": None if daily_vol is None else round(1.645 * daily_vol * total, 2),
        "history_days": length,
        "assets": per_asset,
        "warnings": warnings,
    }


async def find_opportunities(
    market: Market, asset_ids: list[str] | None = None
) -> dict[str, Any]:
    config = load_config()
    rules = config["rules"]
    held = {h["id"] for h in config["holdings"]}
    ids = asset_ids or list(dict.fromkeys([*config["watchlist"], *held]))
    signals, errors = [], []

    for asset_id in ids:
        try:
            a = await analyze_asset(market, asset_id)
        except MarketError as exc:
            errors.append({"id": asset_id, "error": str(exc)})
            continue
        found = []
        rsi14, drop = a["rsi14"], a["change_7d_pct"]
        if rsi14 is not None and rsi14 < rules["rsi_oversold"]:
            found.append(("posible compra", f"RSI en {rsi14} (sobreventa)"))
        if drop is not None and drop <= -rules["drop_7d_pct"]:
            found.append(("posible compra", f"cayó {abs(drop)} % en 7 días"))
        if asset_id in held and rsi14 is not None and rsi14 > rules["rsi_overbought"]:
            found.append(("posible toma de ganancias", f"RSI en {rsi14} (sobrecompra)"))
        for kind, reason in found:
            signals.append(
                {
                    "id": asset_id,
                    "type": kind,
                    "reason": reason,
                    "price_usd": a["price_usd"],
                    "trend": a["trend"],
                    "in_portfolio": asset_id in held,
                }
            )

    return {
        "checked": ids,
        "rules": rules,
        "signals": signals,
        "errors": errors,
        "note": "Son señales técnicas para revisar, no recomendaciones ni garantías.",
    }


async def generate_trade_plan(
    market: Market, asset_id: str, capital_usd: float, risk_pct: float = 1.0
) -> dict[str, Any]:
    if capital_usd <= 0 or not 0 < risk_pct <= 100:
        raise MarketError("capital_usd debe ser positivo y risk_pct estar entre 0 y 100.")
    closes = await market.daily_closes(asset_id, HISTORY_DAYS)
    entry = closes[-1]
    move = ind.average_daily_move(closes)
    if not move:
        raise MarketError(f"'{asset_id}' no tiene movimiento reciente para calcular el stop.")

    # El stop queda a 2 movimientos diarios medios: fuera del ruido normal del activo.
    stop_distance = min(2 * move, 0.5)
    stop = entry * (1 - stop_distance)
    max_loss = capital_usd * risk_pct / 100
    position_usd = min(max_loss / stop_distance, capital_usd)

    return {
        "id": asset_id,
        "entry_usd": entry,
        "stop_loss_usd": stop,
        "stop_distance_pct": _pct(stop_distance),
        "targets_usd": {
            "1.5R": entry * (1 + 1.5 * stop_distance),
            "3R": entry * (1 + 3 * stop_distance),
        },
        "position_size_usd": round(position_usd, 2),
        "position_size_units": position_usd / entry,
        "max_loss_usd": round(position_usd * stop_distance, 2),
        "capital_usd": capital_usd,
        "risk_pct": risk_pct,
        "execution": "manual: la orden la colocas tú en la app",
    }


async def send_alert(message: str) -> dict[str, Any]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise MarketError(
            "Faltan TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID; la alerta no se envió."
        )
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": message[:4096]},
            )
        except httpx.HTTPError as exc:
            # No se incluye la URL en el error: contiene el token del bot.
            raise MarketError(
                f"No se pudo conectar con Telegram ({type(exc).__name__})."
            ) from None
    if response.status_code != 200:
        raise MarketError(
            f"Telegram rechazó la alerta ({response.status_code}): {response.text[:200]}"
        )
    return {"sent": True, "characters": len(message[:4096])}
