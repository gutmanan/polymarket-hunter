from __future__ import annotations

from typing import Any

from polymarket_hunter.core.notifier.formatter.place_order_formatter import format_trade_record_message
from polymarket_hunter.dal.datamodel.order_request import OrderRequest
from polymarket_hunter.dal.datamodel.trade_record import TradeRecord
from polymarket_hunter.dal.datamodel.trade_snapshot import TradeSnapshot
from polymarket_hunter.dal.db import write_object
from polymarket_hunter.dal.notification_store import RedisNotificationStore
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


class TradeService:
    def __init__(self) -> None:
        self._notifier = RedisNotificationStore()

    async def serve(self, payload: dict[str, Any]) -> None:
        if payload["action"] != "add":
            return

        try:
            req = OrderRequest.model_validate_json(payload["order_request"])
            tr = TradeRecord.model_validate_json(payload["trade_record"])
        except Exception as e:
            logger.warning("Invalid TradeRecord payload: %s", e, exc_info=True)
            return

        snapshot = self._build_snapshot(req, tr)
        await write_object(snapshot)
        await self._notifier.send_message(format_trade_record_message(tr))

    def _build_snapshot(self, req: OrderRequest, tr: TradeRecord) -> TradeSnapshot:
        return TradeSnapshot(
            order_id=tr.order_id,
            transaction_hash=tr.transaction_hash,
            market_id=tr.market_id,
            asset_id=tr.asset_id,
            slug=tr.slug,
            side=tr.side,
            outcome=tr.outcome,
            status=tr.status,
            active=tr.active,
            trader_side=tr.trader_side,
            matched_amount=tr.matched_amount,
            price=tr.price,
            fee_rate_bps=tr.fee_rate_bps,
            request_source=req.request_source,
            strategy_name=req.strategy_name,
            rule_name=req.rule_name,
            strategy_action=StrategyAction.model_dump(req.action),
            matched_ts=tr.matched_ts
        )
