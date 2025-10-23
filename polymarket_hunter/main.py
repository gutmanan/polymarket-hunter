import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from polymarket_hunter.api.health_router import router as health_router
from polymarket_hunter.api.slugs_router import router as slugs_router
from polymarket_hunter.api.webhook_router import router as webhook_router
from polymarket_hunter.config.settings import settings
from polymarket_hunter.core.subscription_manager import SubscriptionManager
from polymarket_hunter.scheduler.scheduler import build_scheduler
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    manager = SubscriptionManager()
    await manager.start()
    app.state.manager = manager
    scheduler = build_scheduler(manager)
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

    # Routers
    app.include_router(health_router)
    app.include_router(slugs_router)
    app.include_router(webhook_router)

    return app


app = create_app()
