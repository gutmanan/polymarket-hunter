from typing import Dict, Any

from polymarket_hunter.core.subscriber.websocket.handler.handlers import MessageHandler, MessageContext
from polymarket_hunter.dal.datamodel.trade_record import TradeRecord
from polymarket_hunter.dal.notification_store import RedisNotificationStore
from polymarket_hunter.dal.trade_record_store import RedisTradeRecordStore
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)

class OrderHandler(MessageHandler):

    event_types = ["order"]

    def __init__(self):
        self._trade_store = RedisTradeRecordStore()
        self._notifier = RedisNotificationStore()

    async def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        logger.info(f"Received order: {msg}")
        # market = ctx.markets[msg["market"]]  # ensure market is known
        # tr = await self._merge_trade_record(market, msg)
        # await self._trade_store.add(tr)

    async def _merge_trade_record(self, market: Dict[str, Any], msg: Dict[str, Any]) -> "TradeRecord":
        market_id = msg["market"]
        asset_id = msg["asset_id"]
        side = msg["side"]
        order_id = msg["id"]

        tr = await self._trade_store.get(market_id, asset_id, side, order_id)

        ev_type = (msg.get("type") or "").upper()
        status = (msg.get("status") or "").upper() or "LIVE"
        size_orig = float(msg.get("original_size"))
        size_mat = float(msg.get("size_matched"))
        price = float(msg.get("price"))
        placed_ts = msg.get("created_at")
        ev_ts = msg.get("timestamp")

        if tr is None:
            # create new record
            tr = TradeRecord(
                market_id=market_id,
                asset_id=asset_id,
                side=side,
                order_id=order_id,
                order_owner=msg.get("order_owner"),
                order_type=msg.get("order_type"),
                slug=market.get("slug"),
                outcome=msg.get("outcome"),
                associate_trades=msg.get("associate_trades"),
                matched_amount=size_mat,
                size=size_orig,
                price=price,
                status=status,
                active=True,
                raw_events=[dict(msg)],
                placed_ts=placed_ts if ev_type == "PLACEMENT" else placed_ts or ev_ts,
            )
            return tr

        new_matched = tr.matched_amount + size_mat

        bumped_match_ts = tr.matched_ts
        if new_matched > (tr.matched_amount or 0.0):
            bumped_match_ts = ev_ts or tr.matched_ts

        associate_trades = tr.associate_trades
        associate_trades.extend(msg.get("associate_trades") or [])

        raw_events = tr.raw_events
        raw_events.append(dict(msg))
        if len(raw_events) > 100:
            raw_events = set(raw_events[-100:])

        active = tr.active
        if ev_type == "CANCELLATION":
            active = False

        return tr.model_copy(update={
            "associate_trades": new_assoc,
            "matched_amount": new_matched,
            "status": status or tr.status,
            "price": price or tr.price,
            "size": size_orig or tr.size,
            "active": active,
            "raw_events": raw_events,
            "placed_ts": tr.placed_ts or placed_ts or ev_ts,
            "matched_ts": bumped_match_ts,
            "order_owner": tr.order_owner or msg.get("order_owner"),
            "order_type": tr.order_type or msg.get("order_type"),
            "slug": tr.slug or market.get("slug"),
            "outcome": tr.outcome or msg.get("outcome"),
        })