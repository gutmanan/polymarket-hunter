from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Protocol, Any, Dict, List

from src.core.client.clob import CLOBClient
from src.core.client.data import DataClient
from src.core.client.gamma import GammaClient


def to_map(objs: list[dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    return {obj[key]: obj for obj in objs}

class MessageHandler(Protocol):
    def can_handle(self, msg: Dict[str, Any]) -> bool:
        """Fast predicate: return True if this handler wants this message."""
        ...

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
    """Async dispatcher for async handlers only."""
    def __init__(self, handlers: List[MessageHandler], ctx: "MessageContext", *, concurrent: bool = True):
        self.handlers = handlers
        self.ctx = ctx
        self.concurrent = concurrent

    async def dispatch(self, msg: Dict[str, Any]) -> None:
        matched = False
        coros: List[asyncio.Task] | List[Any] = []

        for h in self.handlers:
            if not h.can_handle(msg):
                continue
            matched = True
            if self.concurrent:
                coros.append(asyncio.create_task(h.handle(msg, self.ctx)))
            else:
                await h.handle(msg, self.ctx)

        if coros:
            results = await asyncio.gather(*coros, return_exceptions=True)
            # log handler exceptions without crashing the router
            for h, res in zip([hh for hh in self.handlers if hh.can_handle(msg)], results):
                if isinstance(res, Exception):
                    self.ctx.logger.exception(f"Handler {h.__class__.__name__} failed: {res}")

        if not matched:
            self.ctx.logger.debug(f"No handler matched type={msg.get('event_type')} keys={list(msg.keys())}")
