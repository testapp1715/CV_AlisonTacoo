"""Servidor MCP del agente de inversión (análisis y alertas, compras manuales)."""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

import agent
from market import Market

mcp = MCPServer(
    "agente-inversion",
    instructions=(
        "Herramientas de análisis de criptomonedas con datos públicos de CoinGecko. "
        "Los activos se identifican por su id de CoinGecko (por ejemplo 'bitcoin'); "
        "usa search_asset si solo conoces el nombre o el símbolo. El portafolio sale "
        "de un archivo local que el usuario actualiza a mano. Ninguna herramienta "
        "ejecuta operaciones. Presenta las señales como información para decidir, "
        "nunca como garantía de resultado."
    ),
)
market = Market()


@mcp.tool()
async def search_asset(query: str) -> list[dict[str, Any]]:
    """Busca un activo por nombre o símbolo y devuelve su id de CoinGecko."""
    return await market.search(query)


@mcp.tool()
async def get_market_prices(
    asset_ids: list[str], vs_currency: str = "usd"
) -> dict[str, Any]:
    """Precio actual, variación en 24 h y capitalización de uno o varios activos."""
    return await market.prices(asset_ids, vs_currency)


@mcp.tool()
async def get_portfolio() -> dict[str, Any]:
    """Posiciones del usuario valoradas a precio actual, con peso y ganancia o pérdida."""
    return await agent.get_portfolio(market)


@mcp.tool()
async def analyze_asset(asset_id: str, days: int = 90) -> dict[str, Any]:
    """Análisis técnico de un activo: tendencia, medias, RSI, volatilidad y caída máxima."""
    return await agent.analyze_asset(market, asset_id, days)


@mcp.tool()
async def calculate_risk() -> dict[str, Any]:
    """Riesgo del portafolio: concentración, volatilidad, caída máxima y pérdida diaria estimada."""
    return await agent.calculate_risk(market)


@mcp.tool()
async def find_opportunities(asset_ids: list[str] | None = None) -> dict[str, Any]:
    """Aplica las reglas configuradas a la lista de seguimiento (o a los ids dados) y devuelve las señales."""
    return await agent.find_opportunities(market, asset_ids)


@mcp.tool()
async def generate_trade_plan(
    asset_id: str, capital_usd: float, risk_pct: float = 1.0
) -> dict[str, Any]:
    """Calcula entrada, stop, objetivos y tamaño de posición arriesgando risk_pct del capital. No ejecuta nada."""
    return await agent.generate_trade_plan(market, asset_id, capital_usd, risk_pct)


@mcp.tool()
async def send_alert(message: str) -> dict[str, Any]:
    """Envía un mensaje al Telegram del usuario."""
    return await agent.send_alert(message)


if __name__ == "__main__":
    mcp.run()
