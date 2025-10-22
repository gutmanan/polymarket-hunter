import asyncio
from typing import Set

from src.core.ws_client import MarketWSClient
from src.persistence.slug_store import RedisSlugStore
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class SubscriptionManager:
    """
    Coordinates slug set across Redis and the local WebSocket client.
    Loads initial slugs from Redis on start and keeps listening to PubSub events.
    """

    def __init__(self, store: RedisSlugStore):
        self._store = store
        self._ws_client = MarketWSClient([])
        self._task: asyncio.Task | None = None
        self._events_task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self._slugs: Set[str] = set()

    # API expected
    def get_slugs(self) -> Set[str]:
        return set(self._slugs)

    async def add_slug(self, slug: str) -> None:
        await self._store.add(slug)

    async def remove_slug(self, slug: str) -> None:
        await self._store.remove(slug)

    async def update_slugs(self, new_slugs: Set[str]) -> None:
        await self._store.replace_all(new_slugs)

    # lifecycle
    async def start(self):
        # load initial
        slugs = await self._store.list()
        await self._apply_local_slugs(set(slugs))
        # start ws client thread
        await self._ws_client.start()
        # subscribe to events
        self._events_task = asyncio.create_task(self._events_loop())

    async def stop(self):
        if self._events_task:
            self._events_task.cancel()
            try:
                await self._events_task
            except Exception:
                pass
        await self._ws_client.stop()

    async def _events_loop(self):
        async for event in self._store.subscribe_events():
            action = event.get("action")
            slug = event.get("slug")
            current = await self._store.list()
            await self._apply_local_slugs(set(current))

    async def _apply_local_slugs(self, new_slugs: Set[str]):
        async with self._lock:
            if new_slugs == self._slugs:
                return
            removed = self._slugs - new_slugs
            added = new_slugs - self._slugs
            logger.info(f"Updating slugs; +{len(added)} -{len(removed)}")
            self._slugs = set(new_slugs)
            # update ws client with full slug list; it will restart connection
            await self._ws_client.update_slugs(sorted(self._slugs))
