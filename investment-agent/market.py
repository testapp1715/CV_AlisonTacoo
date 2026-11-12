"""Cliente mínimo de CoinGecko (datos públicos de mercado)."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
from mcp.server.mcpserver.exceptions import ToolError

BASE_URL = "https://api.coingecko.com/api/v3"
CACHE_SECONDS = 60


class MarketError(ToolError):
    """Fallo previsto: como ToolError, su mensaje llega tal cual al modelo."""


class Market:
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        headers = {"accept": "application/json"}
        api_key = os.environ.get("COINGECKO_API_KEY")
        if api_key:
            headers["x-cg-demo-api-key"] = api_key
        self._client = client or httpx.AsyncClient(
            base_url=BASE_URL, headers=headers, timeout=20
        )
        self._cache: dict[str, tuple[float, Any]] = {}

    async def _get(self, path: str, **params: Any) -> Any:
        key = path + "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        hit = self._cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
        try:
            response = await self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise MarketError(f"No se pudo conectar con CoinGecko: {exc}") from exc
        if response.status_code == 429:
            raise MarketError(
                "CoinGecko rechazó la petición por límite de uso. Espera un minuto "
                "o configura COINGECKO_API_KEY."
            )
        if response.status_code == 404:
            raise MarketError(
                f"CoinGecko no reconoce el activo pedido ({path}). "
                "Usa search_asset para encontrar el id correcto."
            )
        if response.status_code >= 400:
            raise MarketError(
                f"CoinGecko respondió {response.status_code}: {response.text[:200]}"
            )
        data = response.json()
        self._cache[key] = (time.monotonic(), data)
        return data

    async def search(self, query: str) -> list[dict[str, Any]]:
        data = await self._get("/search", query=query)
        return [
            {
                "id": coin["id"],
                "symbol": coin["symbol"],
                "name": coin["name"],
                "market_cap_rank": coin.get("market_cap_rank"),
            }
            for coin in data.get("coins", [])[:10]
        ]

    async def prices(self, ids: list[str], vs_currency: str = "usd") -> dict[str, Any]:
        if not ids:
            return {}
        vs = vs_currency.lower()
        data = await self._get(
            "/simple/price",
            ids=",".join(sorted(set(ids))),
            vs_currencies=vs,
            include_24hr_change="true",
            include_market_cap="true",
            include_last_updated_at="true",
        )
        result = {}
        for asset_id in ids:
            row = data.get(asset_id)
            if not row or vs not in row:
                result[asset_id] = {"error": "id no encontrado en CoinGecko"}
                continue
            result[asset_id] = {
                "price": row[vs],
                "change_24h_pct": row.get(f"{vs}_24h_change"),
                "market_cap": row.get(f"{vs}_market_cap"),
                "last_updated_at": row.get("last_updated_at"),
                "currency": vs,
            }
        return result

    async def daily_closes(
        self, asset_id: str, days: int = 90, vs_currency: str = "usd"
    ) -> list[float]:
        """Precios diarios, del más antiguo al más reciente."""
        data = await self._get(
            f"/coins/{asset_id}/market_chart",
            vs_currency=vs_currency.lower(),
            days=days,
            interval="daily",
        )
        closes = [point[1] for point in data.get("prices", [])]
        if len(closes) < 2:
            raise MarketError(f"No hay historial de precios para '{asset_id}'.")
        return closes
