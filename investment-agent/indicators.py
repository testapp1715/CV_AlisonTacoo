"""Indicadores calculados sobre una serie de precios diarios (antiguo -> reciente)."""

from __future__ import annotations

import math


def sma(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def rsi(closes: list[float], period: int = 14) -> float | None:
    """RSI con suavizado de Wilder."""
    if len(closes) <= period:
        return None
    changes = [b - a for a, b in zip(closes, closes[1:])]
    avg_gain = sum(max(c, 0) for c in changes[:period]) / period
    avg_loss = sum(max(-c, 0) for c in changes[:period]) / period
    for change in changes[period:]:
        avg_gain = (avg_gain * (period - 1) + max(change, 0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-change, 0)) / period
    if avg_loss == 0:
        return 100.0
    return 100 - 100 / (1 + avg_gain / avg_loss)


def returns(closes: list[float]) -> list[float]:
    return [b / a - 1 for a, b in zip(closes, closes[1:]) if a]


def volatility(daily_returns: list[float]) -> float | None:
    """Desviación estándar de los retornos diarios."""
    n = len(daily_returns)
    if n < 2:
        return None
    mean = sum(daily_returns) / n
    return math.sqrt(sum((r - mean) ** 2 for r in daily_returns) / (n - 1))


def annualize(daily_vol: float | None) -> float | None:
    # Cripto cotiza los 365 días del año.
    return None if daily_vol is None else daily_vol * math.sqrt(365)


def max_drawdown(closes: list[float]) -> float:
    """Mayor caída desde un máximo previo, como fracción negativa (-0.35 = -35 %)."""
    peak = closes[0]
    worst = 0.0
    for price in closes:
        peak = max(peak, price)
        if peak:
            worst = min(worst, price / peak - 1)
    return worst


def change(closes: list[float], days: int) -> float | None:
    if len(closes) <= days or not closes[-days - 1]:
        return None
    return closes[-1] / closes[-days - 1] - 1


def average_daily_move(closes: list[float], period: int = 14) -> float | None:
    """Movimiento diario medio en valor absoluto, como fracción del precio."""
    moves = [abs(r) for r in returns(closes)[-period:]]
    return sum(moves) / len(moves) if moves else None
