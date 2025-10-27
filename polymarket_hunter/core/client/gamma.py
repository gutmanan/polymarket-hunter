import os
from functools import lru_cache
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()


class GammaClient:
    def __init__(self):
        self.gamma_url = os.environ.get("GAMMA_HOST", "https://api.gamma.markets")
        self.markets_endpoint = self.gamma_url + "/markets"
        self.events_endpoint = self.gamma_url + "/events"

    def get_market(self, market_id: int) -> Any:
        url = self.markets_endpoint + "/" + str(market_id)
        response = httpx.get(url)
        return response.json()

    def get_market_by_slug(self, slug: str) -> Any:
        url = f"{self.markets_endpoint}/slug/{slug}"
        response = httpx.get(url, params={"include_tag": True})
        return response.json()

    def get_markets(self, querystring_params=None) -> Any:
        response = httpx.get(self.markets_endpoint, params=querystring_params)
        return response.json()

    def get_current_markets(self, limit=100) -> Any:
        return self.get_markets(
            querystring_params={
                "active": True,
                "closed": False,
                "archived": False,
                "limit": limit,
            }
        )

    def get_all_current_markets(self, limit=100) -> Any:
        offset = 0
        all_markets = []
        while True:
            params = {
                "active": True,
                "closed": False,
                "archived": False,
                "limit": limit,
                "offset": offset,
            }
            market_batch = self.get_markets(querystring_params=params)
            all_markets.extend(market_batch)

            if len(market_batch) < limit:
                break
            offset += limit

        return all_markets

@lru_cache(maxsize=1)
def get_gamma_client() -> GammaClient:
    return GammaClient()


if __name__ == "__main__":
    gamma = GammaClient()
    res = gamma.get_markets({'slug': 'will-trump-meet-with-xi-jinping-by-october-31'})
    # res = gamma.get_market(40)
    print(res)