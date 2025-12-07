import json
import time

from fastapi import APIRouter
from sqlmodel import select

from polymarket_hunter.api.datamodel.order_request import ApiOrderRequest
from polymarket_hunter.api.datamodel.order_update_request import ApiOrderUpdateRequest
from polymarket_hunter.core.client.gamma import get_gamma_client
from polymarket_hunter.dal.datamodel.order_request import OrderRequest, RequestSource
from polymarket_hunter.dal.datamodel.strategy_action import Side, StrategyAction
from polymarket_hunter.dal.datamodel.trade_snapshot import TradeSnapshot
from polymarket_hunter.dal.db import get_object, write_object
from polymarket_hunter.dal.order_request_store import RedisOrderRequestStore
from polymarket_hunter.dal.trade_record_store import RedisTradeRecordStore
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/order", tags=["User Orders"])

order_store = RedisOrderRequestStore()
trade_store = RedisTradeRecordStore()

gamma = get_gamma_client()


async def _derive_market_keys(slug: str, outcome: str):
    market = await gamma.get_market_by_slug(slug)
    market_id = market["conditionId"]
    outcomes = json.loads(market["outcomes"])
    token_ids = json.loads(market["clobTokenIds"])
    token_id = token_ids[outcomes.index(outcome)]
    return market_id, token_id


@router.get("/{slug}/{outcome}/{side}")
async def get_order(slug: str, outcome: str, side: str):
    market_id, token_id = await _derive_market_keys(slug, outcome)
    return await order_store.get(market_id, token_id, side)


@router.put("")
async def place_order(payload: ApiOrderRequest):
    market_id, token_id = await _derive_market_keys(payload.slug, payload.outcome)
    return await order_store.add(OrderRequest(
        market_id=market_id,
        asset_id=token_id,
        outcome=payload.outcome,
        price=payload.price,
        size=payload.size,
        side=payload.side,
        tif=payload.tif,
        order_type=payload.order_type,
        request_source=RequestSource.API_CALL,
        action=StrategyAction(
            side=payload.side,
            size=payload.size,
            outcome=payload.outcome
        ),
        strategy_name="Manual",
        rule_name="Manual"
    ))


@router.post("")
async def update_order(payload: ApiOrderUpdateRequest):
    market_id, asset_id = await _derive_market_keys(payload.slug, payload.outcome)
    existing_order = await order_store.get(market_id, asset_id, Side.BUY)
    if not existing_order:
        return {"error": "Active order not found"}, 404

    updated_action = existing_order.action.model_copy(update={
        "slippage": payload.slippage if payload.slippage is not None else existing_order.action.slippage,
        "stop_loss": payload.stop_loss if payload.stop_loss is not None else existing_order.action.stop_loss,
        "take_profit": payload.take_profit if payload.take_profit is not None else existing_order.action.take_profit
    })

    updated_order = existing_order.model_copy(update={"action": updated_action})
    await order_store.update(updated_order)

    statement = select(TradeSnapshot).where(True,
                                            TradeSnapshot.market_id == market_id,
                                            TradeSnapshot.asset_id == asset_id,
                                            TradeSnapshot.side == Side.BUY
                                            )
    db_snapshot = await get_object(statement)

    if db_snapshot:
        db_snapshot.strategy_action = updated_action.model_dump()
        await write_object(db_snapshot)

    return {"status": "ok", "message": "Risk parameters updated successfully in Redis and Postgres."}


@router.post("/close/{slug}/{outcome}")
async def close_position(slug: str, outcome: str):
    market_id, asset_id = await _derive_market_keys(slug, outcome)
    existing_order = await order_store.get(market_id, asset_id, Side.BUY)
    if not existing_order:
        return {"error": "Active order not found"}, 404

    statement = select(TradeSnapshot).where(True,
                                            TradeSnapshot.market_id == market_id,
                                            TradeSnapshot.asset_id == asset_id,
                                            TradeSnapshot.side == Side.BUY
                                            )
    db_snapshot = await get_object(statement)
    if not db_snapshot:
        return {"error": "No trade snapshot found for this position"}, 404

    new_snapshot = db_snapshot.model_copy(update={
        "id": None,
        "order_id": db_snapshot.order_id.replace("0x", "1x"),
        "side": Side.SELL,
        "created_ts": time.time(),
        "updated_ts": time.time()
    })
    await write_object(new_snapshot)

    return {"status": "ok", "message": "Position closed successfully in Redis and Postgres."}
