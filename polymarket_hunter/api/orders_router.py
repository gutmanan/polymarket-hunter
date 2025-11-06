import json
from typing import Any

from fastapi import APIRouter

from polymarket_hunter.core.client.clob import get_clob_client
from polymarket_hunter.core.client.gamma import get_gamma_client
from polymarket_hunter.dal.datamodel.strategy_action import TIF
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()
gamma = get_gamma_client()
clob = get_clob_client()

@router.post("/orders/place")
async def place_order(payload: dict[str, Any]):
    slug = payload.get("slug")
    outcome = payload.get("outcome")
    market = await gamma.get_market_by_slug(slug)
    token_ids = json.loads(market["clobTokenIds"])
    outcomes = json.loads(market["outcomes"])
    token_id = token_ids[outcomes.index(outcome)]
    return clob.execute_limit_order(
        token_id=token_id,
        price=payload["price"],
        size=payload["size"],
        side=payload["side"],
        tif=payload.get("tif", TIF.FOK)
    )
