import json

from fastapi import APIRouter

from polymarket_hunter.core.client.clob import get_clob_client
from polymarket_hunter.core.client.gamma import get_gamma_client
from polymarket_hunter.dal.trade_record_store import RedisTradeRecordStore

router = APIRouter()
gamma = get_gamma_client()
clob = get_clob_client()
trade_store = RedisTradeRecordStore()


@router.get("/trades")
async def list_trades():
    return {"trades": await trade_store.list_keys()}


@router.get("/trade/{slug}/{outcome}/{side}")
async def get_trade(slug: str, outcome: str, side: str):
    market = await gamma.get_market_by_slug(slug)
    market_id = market["conditionId"]
    token_ids = json.loads(market["clobTokenIds"])
    outcomes = json.loads(market["outcomes"])
    token_id = token_ids[outcomes.index(outcome)]
    return await trade_store.get_active(market_id, token_id, side)


@router.delete("/trades")
async def delete_trades():
    for key in await trade_store.list_keys():
        parts = key.split(":")
        await trade_store.remove(parts[0], parts[1], parts[2], parts[3])
    return {"trades": await trade_store.list_keys()}
