import time
from typing import Dict, Any, Optional

from src.ws.handler.handlers import MessageHandler, MessageContext



class PriceChangeHandler(MessageHandler):
    def __init__(self):
        pass

    def can_handle(self, msg: Dict[str, Any]) -> bool:
        return msg.get("event_type") == "price_change"

    def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        now = time.time()
        market = ctx.markets[msg["market"]]
