from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from polymarket_hunter.api.health_router import router as health_router
from polymarket_hunter.api.market_router import router as slugs_router
from polymarket_hunter.api.orders_router import router as orders_router
from polymarket_hunter.api.trades_router import router as trades_router
from polymarket_hunter.api.webhook_router import router as webhook_router
from polymarket_hunter.config.settings import settings
from polymarket_hunter.core.service.scheduler_service import SchedulerService
from polymarket_hunter.core.subscriber.context_subscriber import ContextSubscriber
from polymarket_hunter.core.subscriber.market_subscriber import MarketSubscriber
from polymarket_hunter.core.subscriber.notification_subscriber import NotificationsSubscriber
from polymarket_hunter.core.subscriber.order_subscriber import OrdersSubscriber
from polymarket_hunter.core.subscriber.trade_subscriber import TradesSubscriber
from polymarket_hunter.core.subscriber.user_subscriber import UserSubscriber
from polymarket_hunter.dal import create_db_and_tables
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_db_and_tables()

    market_subscriber = MarketSubscriber()
    await market_subscriber.start()

    user_subscriber = UserSubscriber()
    await user_subscriber.start()

    context_subscriber = ContextSubscriber()
    await context_subscriber.start()

    orders_subscriber = OrdersSubscriber()
    await orders_subscriber.start()

    trades_subscriber = TradesSubscriber()
    await trades_subscriber.start()

    notification_subscriber = NotificationsSubscriber()
    await notification_subscriber.start()

    scheduler = SchedulerService(market_subscriber)
    scheduler.start()

    try:
        yield
    except Exception as e:
        logger.exception(f"Exception occurred while starting the app: {e}")
        scheduler.reload()
    finally:
        await market_subscriber.stop()
        await user_subscriber.stop()
        await context_subscriber.stop()
        await orders_subscriber.stop()
        await trades_subscriber.stop()
        await notification_subscriber.stop()
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
    app.include_router(orders_router)
    app.include_router(trades_router)

    return app


app = create_app()
