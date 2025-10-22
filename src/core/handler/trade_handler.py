from typing import Dict, Any

from src.core.handler.handlers import MessageHandler, MessageContext


class TradeHandler(MessageHandler):
    def can_handle(self, msg: Dict[str, Any]) -> bool:
        return msg["event_type"] == "last_trade_price"

    async def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        market = ctx.markets[msg["market"]]  # ensure market is known
        ctx.logger.debug(f"{market['slug']} last trade price: {msg['price']} at {msg['timestamp']}")

