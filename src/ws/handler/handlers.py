from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol, Any, Dict, List

from src.client.clob import CLOBClient
from src.client.data import DataClient
from src.client.gamma import GammaClient


def to_map(objs: list[dict[str, Any]], key: str) -> Dict[str, Dict[str, Any]]:
    return {obj[key]: obj for obj in objs}

class MessageHandler(Protocol):
    def can_handle(self, msg: Dict[str, Any]) -> bool:
        """Fast predicate: return True if this handler wants this message."""
        ...

    def handle(self, msg: Dict[str, Any], ctx: "MessageContext") -> None:
        """Do the work. Raise only for unexpected errors."""
        ...

class MessageContext:
    """
    Shared context DI container for handlers.
    Put things like logger, caches, clients, config, queues, etc.
    """
    def __init__(self, *, logger, markets: list[dict[str, Any]], gamma_client=None, clob_client=None, data_client=None):
        self.logger = logger
        self.markets = to_map(markets, key="conditionId")
        self.gamma_client: GammaClient = gamma_client
        self.clob_client: CLOBClient = clob_client
        self.data_client: DataClient = data_client

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

class MessageRouter:
    """Keeps a registry of handlers and dispatches messages to each matching one."""
    def __init__(self, handlers: List[MessageHandler], ctx: MessageContext):
        self.handlers = handlers
        self.ctx = ctx

    def dispatch(self, msg: Dict[str, Any]) -> None:
        matched = False
        for h in self.handlers:
            try:
                if h.can_handle(msg):
                    matched = True
                    h.handle(msg, self.ctx)
            except Exception as e:
                self.ctx.logger.exception(f"Handler {h.__class__.__name__} failed: {e}")
        if not matched:
            # optional: debug unmatched messages
            self.ctx.logger.debug(f"No handler matched message type={msg['event_type']} keys={list(msg.keys())}")
