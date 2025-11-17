from typing import Dict, Any

from polymarket_hunter.core.subscriber.websocket.handler.handlers import MessageHandler, MessageContext
from polymarket_hunter.dal.notification_store import RedisNotificationStore
from polymarket_hunter.dal.trade_record_store import RedisTradeRecordStore


class OrderHandler(MessageHandler):
    event_types = ["order"]

    def __init__(self):
        self._trade_store = RedisTradeRecordStore()
        self._notifier = RedisNotificationStore()

    async def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        ctx.logger.debug(f"Received order: {msg}")
