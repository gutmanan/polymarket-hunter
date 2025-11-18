import json

from dotenv import load_dotenv
from fastapi import APIRouter

from polymarket_hunter.api.datamodel.order_request import OrderRequest
from polymarket_hunter.core.client.clob import get_clob_client
from polymarket_hunter.core.client.gamma import get_gamma_client
from polymarket_hunter.dal.order_request_store import RedisOrderRequestStore
from polymarket_hunter.utils.logger import setup_logger

load_dotenv()
logger = setup_logger(__name__)
router = APIRouter()
order_store = RedisOrderRequestStore()


@router.get("/order/{slug}/{outcome}/{side}")
async def get_order(slug: str, outcome: str, side: str):
    gamma = get_gamma_client()

    market = await gamma.get_market_by_slug(slug)
    market_id = market["conditionId"]
    token_ids = json.loads(market["clobTokenIds"])
    outcomes = json.loads(market["outcomes"])
    token_id = token_ids[outcomes.index(outcome)]
    return await order_store.get(market_id, token_id, side)


@router.put("/order")
async def place_order(payload: OrderRequest):
    gamma = get_gamma_client()
    clob = get_clob_client()

    market = await gamma.get_market_by_slug(payload.slug)
    token_ids = json.loads(market["clobTokenIds"])
    outcomes = json.loads(market["outcomes"])
    token_id = token_ids[outcomes.index(payload.outcome)]
    print(token_id)
    return clob.execute_limit_order(
        token_id=token_id,
        price=payload.price,
        size=payload.size,
        side=payload.side,
        tif=payload.tif
    )
