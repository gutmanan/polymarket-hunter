import asyncio
from typing import Dict, List

from polymarket_hunter.core.subscriber.websocket.actor.market_actor import MarketActor
from polymarket_hunter.core.subscriber.websocket.handler.handlers import MessageRouter, MessageContext, MessageHandler


class ActorManager:

    def __init__(self, handlers: List[MessageHandler], ctx: MessageContext) -> None:
        self._actors: Dict[str, MarketActor] = {}
        self._router_factory = lambda: MessageRouter(handlers, ctx)

    def get(self, asset_id: str) -> MarketActor:
        if asset_id not in self._actors:
            router = self._router_factory()
            actor = MarketActor(asset_id, router)
            actor.start()
            self._actors[asset_id] = actor
        return self._actors[asset_id]

    async def stop_all(self) -> None:
        await asyncio.gather(*(a.stop() for a in self._actors.values()), return_exceptions=True)
        self._actors.clear()
