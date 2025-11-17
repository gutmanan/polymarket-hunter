from typing import Dict, Any

from polymarket_hunter.core.subscriber.websocket.handler.handlers import MessageHandler, MessageContext


class OrderHandler(MessageHandler):
    event_types = ["order"]

    async def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        ctx.logger.debug(f"Received order: {msg}")
