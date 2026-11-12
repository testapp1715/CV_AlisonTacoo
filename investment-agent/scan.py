"""Revisión programada: evalúa las reglas y avisa por Telegram si hay señales.

Pensado para cron o GitHub Actions, por ejemplo cada hora:
    0 * * * *  cd /ruta/investment-agent && .venv/bin/python scan.py
"""

from __future__ import annotations

import asyncio
import sys

import agent
from market import Market, MarketError


async def main() -> int:
    result = await agent.find_opportunities(Market())
    for error in result["errors"]:
        print(f"[error] {error['id']}: {error['error']}", file=sys.stderr)
    if not result["signals"]:
        print("Sin señales.")
        return 1 if result["errors"] else 0

    lines = ["Señales del agente de inversión:"]
    for s in result["signals"]:
        lines.append(
            f"• {s['id']}: {s['type']} — {s['reason']}. "
            f"Precio {s['price_usd']:,.4g} USD, tendencia {s['trend']}."
        )
    lines.append(result["note"])
    message = "\n".join(lines)
    print(message)
    await agent.send_alert(message)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except MarketError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
