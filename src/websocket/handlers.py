from __future__ import annotations
from typing import Protocol, Any, Dict, List, Optional

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
    def __init__(self, *, logger, gamma_client=None):
        self.logger = logger
        self.gamma_client = gamma_client

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
            self.ctx.logger.debug(f"No handler matched message type={msg.get('type')} keys={list(msg.keys())}")
