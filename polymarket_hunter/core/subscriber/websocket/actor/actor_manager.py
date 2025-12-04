import asyncio
from enum import StrEnum
from typing import Dict, Optional

from polymarket_hunter.core.subscriber.websocket.actor.market_actor import MarketActor
from polymarket_hunter.core.subscriber.websocket.handler.book_handler import BookHandler
from polymarket_hunter.core.subscriber.websocket.handler.handlers import MessageRouter, MessageContext
from polymarket_hunter.core.subscriber.websocket.handler.order_handler import OrderHandler
from polymarket_hunter.core.subscriber.websocket.handler.price_handler import PriceChangeHandler
from polymarket_hunter.core.subscriber.websocket.handler.trade_handler import TradeHandler


class ActorType(StrEnum):
    MARKET = "market"
    USER = "user"


class ActorManager:
    def __init__(self, ctx: MessageContext, actor_type: ActorType) -> None:
        self._actors: Dict[str, MarketActor] = {}
        self._actor_type = actor_type
        self._ctx = ctx

    def _market_router_factory(self, market_id: str) -> MessageRouter:
        handlers = [PriceChangeHandler(), BookHandler()]
        return MessageRouter(market_id, handlers, self._ctx)

    def _user_router_factory(self, market_id: str) -> MessageRouter:
        handlers = [OrderHandler(), TradeHandler()]
        return MessageRouter(market_id, handlers, self._ctx)

    def _get_router(self, market_id: str) -> Optional[MessageRouter]:
        match self._actor_type:
            case ActorType.MARKET:
                return self._market_router_factory(market_id)
            case ActorType.USER:
                return self._user_router_factory(market_id)
            case _:
                raise ValueError(f"Unknown actor type: {self._actor_type}")

    def get(self, market_id: str) -> MarketActor:
        if market_id not in self._actors:
            router = self._get_router(market_id)
            actor = MarketActor(market_id, router)
            actor.start()
            self._actors[market_id] = actor
        return self._actors[market_id]

    async def stop_all(self) -> None:
        await asyncio.gather(*(a.stop() for a in self._actors.values()), return_exceptions=True)
        self._actors.clear()
