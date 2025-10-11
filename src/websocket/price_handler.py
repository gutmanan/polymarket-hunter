from typing import Dict, Any, List

from src.websocket.handlers import MessageHandler, MessageContext


class PriceChangeHandler(MessageHandler):
    def can_handle(self, msg: Dict[str, Any]) -> bool:
        return "price_changes" in msg

    def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        for p_change in msg["price_changes"]:
            ctx.logger.info(f"Price change for {p_change}")
