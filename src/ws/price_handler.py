from typing import Dict, Any

from src.ws.handlers import MessageHandler, MessageContext


class PriceChangeHandler(MessageHandler):
    def can_handle(self, msg: Dict[str, Any]) -> bool:
        return msg["event_type"] == "price_change"

    def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        for p_change in msg["price_changes"]:
            ctx.logger.info(f"Price change for {p_change['price']}")
