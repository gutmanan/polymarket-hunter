import asyncio
import json

from src.client.gamma_client import GammaClient
from src.config.settings import settings
from src.utils.logger import setup_logger
from src.ws.polymarket_ws import PolymarketWebSocket, MARKET_CHANNEL

logger = setup_logger(__name__)


class PolymarketHunter:
    """Main application class"""

    def __init__(self, slugs: list[str]) -> None:
        self.gamma = GammaClient()
        self.ws = PolymarketWebSocket(MARKET_CHANNEL, self.slugs_to_assets(slugs))

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

    def slugs_to_assets(self, slugs: list[str]) -> list[dict]:
        return [
            asset
            for slug in slugs
            for market in self.gamma.get_markets_by_slug(slug)
            for asset in json.loads(market["clobTokenIds"])
        ]


async def main():
    """Application entry point"""
    slugs = [
        "bitcoin-up-or-down-october-11-8am-et"
    ]
    app = PolymarketHunter(slugs)
    await app.start()


if __name__ == "__main__":
    asyncio.run(main())
