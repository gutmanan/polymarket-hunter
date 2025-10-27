from typing import Dict, Any

from polymarket_hunter.core.subscriber.websocket.handler.handlers import MessageHandler, MessageContext


class BookHandler(MessageHandler):
    def can_handle(self, msg: Dict[str, Any]) -> bool:
        return msg["event_type"] == "book"

    async def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        market = ctx.markets[msg["market"]]  # ensure market is known
        ctx.logger.debug(f"{market['slug']} current book {len(msg['bids'])} bids, {len(msg['asks'])} asks")
