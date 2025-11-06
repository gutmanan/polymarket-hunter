import asyncio
import pytest

from polymarket_hunter.core.subscriber.market_subscriber import MarketSubscriber


class FakeStore:
    def __init__(self):
        self.set = set()
        self.events = asyncio.Queue()

    async def add(self, slug: str):
        if slug not in self.set:
            self.set.add(slug)
            await self.events.put({"action": "add", "slug": slug})

    async def remove(self, slug: str):
        if slug in self.set:
            self.set.remove(slug)
            await self.events.put({"action": "remove", "slug": slug})

    async def list(self):
        return sorted(self.set)

    async def replace_all(self, iterable):
        self.set = set(iterable)
        await self.events.put({"action": "replace", "slug": None})

    async def subscribe_events(self):
        while True:
            yield await self.events.get()


class FakeWSClient:
    def __init__(self):
        self.updates = []

    def start(self):
        pass

    def stop(self):
        pass

    def update_slugs(self, slugs):
        self.updates.append(slugs)


@pytest.mark.asyncio
async def test_diff_update_triggers_only_on_changes(monkeypatch):
    store = FakeStore()
    mgr = MarketSubscriber(store)
    # replace internal ws client with fake
    fake_ws = FakeWSClient()
    mgr._ws_client = fake_ws  # type: ignore[attr-defined]

    await mgr.start()
    # initially empty
    assert fake_ws.updates[-1] == []

    await mgr.add_slug("a")
    # events loop applies slugs asynchronously; simulate by applying directly
    await asyncio.sleep(0.01)
    assert fake_ws.updates[-1] == ["a"]

    await mgr.add_slug("a")  # idempotent
    await asyncio.sleep(0.01)
    # no change expected
    assert fake_ws.updates[-1] == ["a"]

    await mgr.add_slug("b")
    await asyncio.sleep(0.01)
    assert set(fake_ws.updates[-1]) == {"a", "b"}

    await mgr.remove_slug("a")
    await asyncio.sleep(0.01)
    assert fake_ws.updates[-1] == ["b"]

    await mgr.stop()
