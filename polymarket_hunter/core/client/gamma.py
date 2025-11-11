import os
from functools import lru_cache
from typing import Any, Dict, Optional, AsyncGenerator

import httpx
from dotenv import load_dotenv

load_dotenv()


class GammaClient:

    def __init__(self, timeout: float = 15.0):
        self.gamma_url = os.environ.get("GAMMA_HOST", "https://api.gamma.markets")
        self.markets_endpoint = f"{self.gamma_url}/markets"
        self.events_endpoint = f"{self.gamma_url}/events"
        self._client = httpx.AsyncClient(timeout=timeout)

    # ---------- Public API ----------

    async def get_market_by_slug(self, slug: str) -> dict[str, Any]:
        url = f"{self.markets_endpoint}/slug/{slug}"
        response = await self._client.get(url, params={"include_tag": True})
        response.raise_for_status()
        return response.json()

    async def get_markets(self, params: Optional[Dict[str, Any]] = None) -> Any:
        response = await self._client.get(self.markets_endpoint, params=params or {})
        response.raise_for_status()
        return response.json()

    async def get_all_markets(self, params: Optional[Dict[str, Any]] = None) -> list[Dict[str, Any]]:
        results: list[Dict[str, Any]] = []
        async for market in self._aiter_markets(params=params):
            results.append(market)
        return results

    async def _aiter_markets(self, page_size: int = 250, params: Optional[Dict[str, Any]] = None) -> AsyncGenerator[Dict[str, Any], None]:
        params = dict(params or {})
        offset = int(params.get("offset") or 0)
        limit = int(params.get("limit") or page_size)
        params["limit"] = limit

        while True:
            params["offset"] = offset
            page = await self.get_markets(params)
            if not page:
                break
            for market in page:
                yield market
            if len(page) < limit:
                break
            offset += limit

    # ---------- Lifecycle ----------

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose()


@lru_cache(maxsize=1)
def get_gamma_client() -> GammaClient:
    return GammaClient()


if __name__ == "__main__":
    import asyncio

    async def main():
        gamma = get_gamma_client()
        res = await gamma.get_market_by_slug("bitcoin-up-or-down-november-5-12pm-et")
        print(res)
        await gamma.aclose()

    asyncio.run(main())
