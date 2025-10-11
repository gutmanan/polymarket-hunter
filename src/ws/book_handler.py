from typing import Dict, Any

from src.ws.handlers import MessageHandler, MessageContext


class BookHandler(MessageHandler):
    def can_handle(self, msg: Dict[str, Any]) -> bool:
        return msg["event_type"] == "book"

    def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        ctx.logger.info(f"Current book {len(msg['bids'])} bids, {len(msg['asks'])} asks")
