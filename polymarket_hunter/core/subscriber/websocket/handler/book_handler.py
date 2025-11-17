from typing import Dict, Any

from polymarket_hunter.core.subscriber.websocket.handler.handlers import MessageHandler, MessageContext


class BookHandler(MessageHandler):
    event_types = ["book"]

    async def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        ctx.logger.debug(f"Received book: {msg}")
