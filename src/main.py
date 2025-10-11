import asyncio
import json

from src.client.gamma_client import GammaClient
from src.config.settings import settings
from src.utils.logger import setup_logger
from src.websocket.handlers import MessageHandler
from src.websocket.polymarket_ws import PolymarketWebSocket, MARKET_CHANNEL

logger = setup_logger(__name__)

class PolymarketHunter:
    """Main application class"""
    
    def __init__(self):
        slug = "bitcoin-up-or-down-october-11-4am-et"
        gamma = GammaClient()
        assets = [json.loads(market.get("clobTokenIds")) for market in gamma.get_markets_by_slug(slug)]
        self.ws_client = PolymarketWebSocket(MARKET_CHANNEL, assets[0])
        self.message_handler = MessageHandler()

    async def start(self) -> None:
        """Start the application"""
        logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
        
        try:
            self.ws_client.run()
        except KeyboardInterrupt:
            logger.info("Shutting down gracefully...")
        except Exception as e:
            logger.error(f"Application error: {e}", exc_info=True)
        finally:
            await self.cleanup()
    
    async def cleanup(self) -> None:
        """Cleanup resources"""
        logger.info("Cleaning up resources...")
        await self.ws_client.close()


async def main():
    """Application entry point"""
    app = PolymarketHunter()
    await app.start()


if __name__ == "__main__":
    asyncio.run(main())
