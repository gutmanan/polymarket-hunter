import asyncio

from src.config.settings import settings
from src.utils.logger import setup_logger
from src.ws.polymarket_ws import PolymarketWebSocket, MARKET_CHANNEL

logger = setup_logger(__name__)


class PolymarketHunter:
    """Main application class"""

    def __init__(self, slugs: list[str]) -> None:
        self.ws = PolymarketWebSocket(MARKET_CHANNEL, slugs)

    async def start(self) -> None:
        """Start the application"""
        logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

        try:
            self.ws.run()
        except KeyboardInterrupt:
            logger.info("Shutting down gracefully...")
        except Exception as e:
            logger.error(f"Application error: {e}", exc_info=True)
        finally:
            await self.cleanup()

    async def cleanup(self) -> None:
        """Cleanup resources"""
        logger.info("Cleaning up resources...")
        self.ws.close()

async def main():
    """Application entry point"""
    slugs = [
        "bitcoin-up-or-down-october-21-3am-et",
    ]
    app = PolymarketHunter(slugs)
    await app.start()

if __name__ == "__main__":
    asyncio.run(main())
