from __future__ import annotations

from typing import Any

from polymarket_hunter.core.client.clob import get_clob_client
from polymarket_hunter.core.client.data import get_data_client
from polymarket_hunter.core.client.gamma import get_gamma_client
from polymarket_hunter.core.notifier.formatter.place_order_formatter import format_trade_record_message
from polymarket_hunter.dal.datamodel.strategy_action import Side
from polymarket_hunter.dal.datamodel.trade_record import TradeRecord
from polymarket_hunter.dal.notification_store import RedisNotificationStore
from polymarket_hunter.dal.trade_record_store import RedisTradeRecordStore
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


class TradeService:
    def __init__(self) -> None:
        self._gamma = get_gamma_client()
        self._clob = get_clob_client()
        self._data = get_data_client()
        self._trade_store = RedisTradeRecordStore()
        self._notifier = RedisNotificationStore()

    # ---------- Public API ----------

    async def update_trade(self, payload: dict[str, Any]) -> None:
        if payload["action"] != "add":
            return

        try:
            rec = TradeRecord.model_validate_json(payload["trade_record"])
        except Exception as e:
            logger.warning("Invalid TradeRecord payload: %s", e, exc_info=True)
            return

        await self.deactivate_opposite(rec)
        await self._notifier.send_message(format_trade_record_message(rec))

    async def deactivate_opposite(self, rec):
        existing_opposite = await self._trade_store.get_latest(
            market_id=rec.market_id,
            asset_id=rec.asset_id,
            side=Side.BUY if rec.side == Side.SELL else Side.SELL
        )
        if existing_opposite:
            deactivate = existing_opposite.model_copy(update={"active": False})
            await self._trade_store.update(deactivate)
