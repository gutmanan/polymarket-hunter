from fastapi import APIRouter

from polymarket_hunter.dal.trade_record_store import RedisTradeRecordStore

router = APIRouter()
trade_store = RedisTradeRecordStore()

@router.get("/trades")
async def list_trades():
    return {"trades": await trade_store.list_keys()}


@router.delete("/trades")
async def delete_trades():
    for key in await trade_store.list_keys():
        parts = key.split(":")
        await trade_store.remove(parts[0], parts[1], parts[2], parts[3])
    return {"trades": await trade_store.list_keys()}
