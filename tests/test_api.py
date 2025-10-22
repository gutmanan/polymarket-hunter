import asyncio
import os
import types
import pytest
from fastapi.testclient import TestClient

from src.main import create_app
from src.api import slugs as slugs_mod
from src.core.subscription_manager import SubscriptionManager


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


@pytest.fixture
def app():
    # Build app with injected fake manager
    from fastapi import FastAPI

    fake_store = FakeStore()
    manager = SubscriptionManager(fake_store)  # uses a real ws client but we won't start lifespan here

    slugs_mod.get_manager = manager
    app = create_app()
    return app


def test_healthz(app):
    client = TestClient(app)
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_slugs_add_list_delete_idempotent(app):
    client = TestClient(app)
    # initially empty
    r = client.get("/slugs")
    assert r.status_code == 200
    assert r.json()["slugs"] == []
    # add
    r = client.post("/slugs", json={"slug": "foo-bar"})
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "foo-bar"
    assert "foo-bar" in body["slugs"]
    # add again idempotent
    r = client.post("/slugs", json={"slug": "foo-bar"})
    assert r.status_code == 200
    # delete
    r = client.delete("/slugs/foo-bar")
    assert r.status_code == 200
    assert "foo-bar" not in r.json()["slugs"]
    # delete again idempotent
    r = client.delete("/slugs/foo-bar")
    assert r.status_code == 200
