from typing import Dict, Any

from polymarket_hunter.core.client.clob import get_clob_client
from polymarket_hunter.core.subscriber.websocket.handler.handlers import MessageHandler, MessageContext
from polymarket_hunter.dal.datamodel.trade_record import TradeRecord
from polymarket_hunter.dal.notification_store import RedisNotificationStore
from polymarket_hunter.dal.trade_record_store import RedisTradeRecordStore
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)

class TradeHandler(MessageHandler):

    event_types = ["trade"]

    def __init__(self):
        self._clob = get_clob_client()
        self._trade_store = RedisTradeRecordStore()
        self._notifier = RedisNotificationStore()

    def _get_order_by_id(self, order_id: str) -> Dict[str, Any]:
        return self._clob.get_order(order_id)

    async def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        if msg["status"] != "CONFIRMED":
            return

        market = ctx.markets[msg["market"]]
        logger.info(f"Received trade: {msg}")
        if msg["trader_side"] == "TAKER":
            order = self._get_order_by_id(msg["taker_order_id"])
            trade = await self._merge_trade_record(market, msg, order)
            await self._trade_store.add(trade)
        elif msg["trader_side"] == "MAKER":
            for order in msg["maker_orders"]:
                trade = await self._merge_trade_record(market, msg, order)
                await self._trade_store.add(trade)

    async def _merge_trade_record(self, market: Dict[str, Any], msg: Dict[str, Any], order: Dict[str, Any]) -> "TradeRecord":
        market_id = msg["market"]
        asset_id = order["asset_id"]
        side = order["side"]
        order_id = order.get("order_id") or order["id"]

        tr = await self._trade_store.get(market_id, asset_id, side, order_id)

        status = (order.get("status") or "").upper() or msg.get("status") or "LIVE"
        size_orig = float(msg.get("size"))
        size_mat = float(order.get("matched_amount") or order.get("size_matched") or 0.0)
        price = float(order.get("price"))

        if tr is None:
            # create new record
            tr = TradeRecord(
                market_id=market_id,
                asset_id=asset_id,
                side=side,
                order_id=order_id,
                slug=market.get("slug"),
                outcome=order.get("outcome"),
                matched_amount=size_mat,
                size=size_orig,
                price=price,
                fee_rate_bps=msg.get("fee_rate_bps"),
                transaction_hash=msg.get("transaction_hash"),
                trader_side=msg.get("trader_side"),
                status=status,
                active=True,
                raw_events=[dict(msg)],
                matched_ts=msg.get("match_time")
            )
            return tr

        new_matched = size_mat or tr.matched_amount

        bumped_match_ts = tr.matched_ts
        if new_matched != (tr.matched_amount or 0.0):
            bumped_match_ts = msg.get("match_time") or tr.matched_ts

        raw_events = tr.raw_events
        raw_events.append(dict(msg))

        active = tr.active
        if status == "FAILED":
            active = False

        return tr.model_copy(update={
            "matched_amount": new_matched,
            "status": status or tr.status,
            "price": price or tr.price,
            "size": size_orig or tr.size,
            "trader_side": msg.get("trader_side"),
            "active": active,
            "raw_events": raw_events,
            "matched_ts": bumped_match_ts
        })
