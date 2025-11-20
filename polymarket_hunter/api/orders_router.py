import json

from fastapi import APIRouter

from polymarket_hunter.api.datamodel.order_request import ApiOrderRequest
from polymarket_hunter.core.client.gamma import get_gamma_client
from polymarket_hunter.dal.datamodel.order_request import OrderRequest, RequestSource
from polymarket_hunter.dal.order_request_store import RedisOrderRequestStore
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter()
order_store = RedisOrderRequestStore()
gamma = get_gamma_client()


@router.get("/order/{slug}/{outcome}/{side}")
async def get_order(slug: str, outcome: str, side: str):
    market = await gamma.get_market_by_slug(slug)
    market_id = market["conditionId"]
    token_ids = json.loads(market["clobTokenIds"])
    outcomes = json.loads(market["outcomes"])
    token_id = token_ids[outcomes.index(outcome)]
    return await order_store.get(market_id, token_id, side)


@router.put("/order")
async def place_order(payload: ApiOrderRequest):
    market = await gamma.get_market_by_slug(payload.slug)
    market_id = market["conditionId"]
    token_ids = json.loads(market["clobTokenIds"])
    outcomes = json.loads(market["outcomes"])
    token_id = token_ids[outcomes.index(payload.outcome)]
    return await order_store.add(OrderRequest(
        market_id=market_id,
        asset_id=token_id,
        outcome=payload.outcome,
        price=payload.price,
        size=payload.size,
        side=payload.side,
        tif=payload.tif,
        order_type=payload.order_type,
        request_source=RequestSource.API_CALL
    ))
