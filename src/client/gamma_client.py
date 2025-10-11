import os
from typing import Any

import requests


class GammaClient:
    def __init__(self):
        self.gamma_url = os.environ.get("GAMMA_HOST", "https://gamma-api.polymarket.com")
        self.markets_endpoint = self.gamma_url + "/markets"
        self.events_endpoint = self.gamma_url + "/events"

    def get_markets_by_slug(self, slug: str) -> Any:
        url = f"{self.events_endpoint}/slug/{slug}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        return data.get("markets", [])

