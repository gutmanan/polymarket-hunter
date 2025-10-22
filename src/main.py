import asyncio
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from src.api.health import router as health_router
from src.api.slugs import router as slugs_router
from src.api.webhook import router as webhook_router
from src.config.settings import settings
from src.core.subscription_manager import SubscriptionManager
from src.persistence.slug_store import RedisSlugStore
from src.scheduler.scheduler import build_scheduler
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


# Dependency injection for routers


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = RedisSlugStore(settings.REDIS_URL)
    manager = SubscriptionManager(store)
    # inject manager into routers
    import src.api.slugs as slugs_mod
    slugs_mod.get_manager = manager

    async def resolve_markets(slugs: list[str]) -> list[dict]:
        return await asyncio.to_thread(manager._ws_client._slugs_to_markets_sync, slugs)

    await manager.start()
    scheduler = build_scheduler(manager, resolve_markets)
    scheduler.start()
    logger.info("Markets scheduler started.")

    try:
        yield
    finally:
        scheduler.shutdown(wait=False)
        await manager.stop()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)

    # CORS permissive for local use
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API Key middleware for write endpoints when API_KEY set
    if settings.API_KEY:
        @app.middleware("http")
        async def api_key_guard(request: Request, call_next: Callable):
            if request.method in ("POST", "DELETE") and request.url.path.startswith(("/slugs", "/webhook")):
                key = request.headers.get("X-API-Key")
                if key != settings.API_KEY:
                    return Response(status_code=401, content="Unauthorized")
            return await call_next(request)

    # Routers
    app.include_router(health_router)
    app.include_router(slugs_router)
    app.include_router(webhook_router)

    return app


app = create_app()
