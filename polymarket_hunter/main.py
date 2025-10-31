from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from polymarket_hunter.api.health_router import router as health_router
from polymarket_hunter.api.slugs_router import router as slugs_router
from polymarket_hunter.api.webhook_router import router as webhook_router
from polymarket_hunter.config.settings import settings
from polymarket_hunter.core.service.scheduler_service import SchedulerService
from polymarket_hunter.core.subscriber.order_subscriber import OrdersSubscriber
from polymarket_hunter.core.subscriber.slug_subscriber import SlugsSubscriber
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    slugs_subscriber = SlugsSubscriber()
    await slugs_subscriber.start()

    orders_subscriber = OrdersSubscriber()
    await orders_subscriber.start()

    app.state.slugs_subscriber = slugs_subscriber
    app.state.orders_subscriber = orders_subscriber

    scheduler = SchedulerService(slugs_subscriber)
    scheduler.start()

    try:
        yield
    except Exception as e:
        logger.exception(f"Exception occurred while starting the app: {e}")
        scheduler.reload()
    finally:
        await slugs_subscriber.stop()
        await orders_subscriber.stop()
        scheduler.stop()


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
