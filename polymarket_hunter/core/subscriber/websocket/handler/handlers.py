from __future__ import annotations

import asyncio
from typing import Protocol, Any, Dict, List, Optional, Iterable

from polymarket_hunter.utils.helper import to_map


class MessageHandler(Protocol):
    event_types: Optional[Iterable[str]] = None

    def can_handle(self, msg: Dict[str, Any]) -> bool:
        return self.event_types is not None and msg["event_type"] in self.event_types

    async def handle(self, msg: Dict[str, Any], ctx: MessageContext) -> None:
        ...


class MessageContext:
    def __init__(self, *, logger, markets: list[dict[str, Any]]):
        self.logger = logger
        self.markets = {}
        self.update_markets(markets)

    def update_markets(self, markets: list[dict[str, Any]]) -> None:
        self.markets = to_map(markets, key="conditionId")


class MessageRouter:
    def __init__(self, market_id: str, handlers: List[MessageHandler], ctx: MessageContext, *, per_handler_timeout_ms: Optional[int] = None) -> None:
        self.market_id = market_id
        self.handlers = handlers
        self.ctx = ctx
        self._timeout = (per_handler_timeout_ms / 1000) if per_handler_timeout_ms else None

    async def dispatch(self, msg: Dict[str, Any]) -> None:
        matched = False
        for h in self.handlers:
            try:
                if not h.can_handle(msg):
                    continue
                matched = True
                if self._timeout:
                    async with asyncio.timeout(self._timeout):
                        await h.handle(msg, self.ctx)
                else:
                    await h.handle(msg, self.ctx)
            except asyncio.TimeoutError:
                self.ctx.logger.warning("Handler %s timed out", h.__class__.__name__)
            except Exception as e:
                self.ctx.logger.error("Handler %s failed: %s", h.__class__.__name__, e)

        if not matched:
            self.ctx.logger.debug("No handler matched event=%s", msg.get("event_type"))
