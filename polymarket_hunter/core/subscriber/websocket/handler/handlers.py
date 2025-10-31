from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Protocol, Any, Dict, List, Optional, Iterable

from polymarket_hunter.core.client.clob import CLOBClient
from polymarket_hunter.core.client.data import DataClient
from polymarket_hunter.core.client.gamma import GammaClient


def to_map(objs: list[dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    return {obj[key]: obj for obj in objs}


class MessageHandler(Protocol):
    event_types: Optional[Iterable[str]] = None

    def can_handle(self, msg: Dict[str, Any]) -> bool:
        return self.event_types is not None and msg["event_type"] in self.event_types

    async def handle(self, msg: Dict[str, Any], ctx: "MessageContext") -> None:
        """Do the work. Raise only for unexpected errors."""
        ...


class MessageContext:
    """
    Shared context DI container for handlers.
    Put things like logger, caches, clients, config, queues, etc.
    """

    def __init__(self, *, logger, markets: list[dict[str, Any]], gamma_client=None, clob_client=None, data_client=None):
        self.logger = logger

        self.gamma_client: GammaClient = gamma_client
        self.clob_client: CLOBClient = clob_client
        self.data_client: DataClient = data_client

        self.markets = {}
        self.update_markets(markets)

    def get_market_resolution_ts(self, condition_id: str) -> float:
        """
        Return the UNIX timestamp (seconds) for the market’s endDate.
        Raises KeyError if condition_id is unknown or endDate missing.
        """
        market = self.markets.get(condition_id)
        if not market:
            raise KeyError(f"Unknown condition_id: {condition_id}")

        end_date = market.get("endDate")
        if not end_date:
            raise KeyError(f"Market {condition_id} missing endDate")

        # Parse ISO string like '2025-10-14T12:00:00Z' into UTC seconds
        if end_date.endswith("Z"):
            end_date = end_date[:-1] + "+00:00"
        dt = datetime.fromisoformat(end_date).astimezone(timezone.utc)
        return dt.timestamp()

    def update_markets(self, markets: list[dict[str, Any]]) -> None:
        self.markets = to_map(markets, key="conditionId")


class MessageRouter:

    def __init__(
            self,
            handlers: List[MessageHandler],
            ctx: "MessageContext",
            *,
            per_handler_timeout_ms: Optional[int] = None,
    ) -> None:
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
                self.ctx.logger.exception("Handler %s failed: %s", h.__class__.__name__, e)

        if not matched:
            self.ctx.logger.debug("No handler matched event=%s", msg.get("event_type"))
