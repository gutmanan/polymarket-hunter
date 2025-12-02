import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from polymarket_hunter.api.health_router import router as health_router
from polymarket_hunter.api.market_router import router as slugs_router
from polymarket_hunter.api.orders_router import router as orders_router
from polymarket_hunter.api.user_router import router as user_router
from polymarket_hunter.config.settings import settings
from polymarket_hunter.core.service.scheduler_service import SchedulerService
from polymarket_hunter.core.subscriber.context_subscriber import ContextSubscriber
from polymarket_hunter.core.subscriber.market_subscriber import MarketSubscriber
from polymarket_hunter.core.subscriber.notification_subscriber import NotificationsSubscriber
from polymarket_hunter.core.subscriber.order_subscriber import OrdersSubscriber
from polymarket_hunter.core.subscriber.trade_subscriber import TradesSubscriber
from polymarket_hunter.core.subscriber.user_subscriber import UserSubscriber
from polymarket_hunter.dal.db import create_db_and_tables
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()

    market_subscriber = MarketSubscriber()
    user_subscriber = UserSubscriber()
    context_subscriber = ContextSubscriber()
    orders_subscriber = OrdersSubscriber()
    trades_subscriber = TradesSubscriber()
    notification_subscriber = NotificationsSubscriber()

    await asyncio.gather(
        market_subscriber.start(),
        user_subscriber.start(),
        context_subscriber.start(),
        orders_subscriber.start(),
        trades_subscriber.start(),
        notification_subscriber.start()
    )

    scheduler = SchedulerService(market_subscriber)
    scheduler.start()

    try:
        yield
    finally:
        logger.info("Starting shutdown procedures...")
        await asyncio.gather(
            market_subscriber.stop(),
            user_subscriber.stop(),
            context_subscriber.stop(),
            orders_subscriber.stop(),
            trades_subscriber.stop(),
            notification_subscriber.stop()
        )
        scheduler.stop()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION, lifespan=lifespan)
    Instrumentator().instrument(app).expose(app)

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
    app.include_router(orders_router)
    app.include_router(user_router)

    return app


app = create_app()
