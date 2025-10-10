import asyncio
import requests
from src.websocket.polymarket_ws import PolymarketWebSocket
from src.websocket.handlers import MessageHandler
from src.utils.logger import setup_logger
from src.config.settings import settings

logger = setup_logger(__name__)


class PolymarketHunter:
    """Main application class"""
    
    def __init__(self):
        self.ws_client = PolymarketWebSocket()
        self.message_handler = MessageHandler()
        
    async def start(self) -> None:
        """Start the application"""
        logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
        
        try:
            # Connect to WebSocket
            await self.ws_client.connect()
            
            # Register message handlers
            self.ws_client.add_handler(self.message_handler.handle_price_update)
            self.ws_client.add_handler(self.message_handler.handle_volume_update)
            self.ws_client.add_handler(self.message_handler.handle_market_creation)
            
            # Subscribe to markets (example market IDs)
            # TODO: Implement dynamic market selection
            markets = [
                "fed-rate-hike-in-2025",
            ]

            API_BASE = "https://gamma-api.polymarket.com"  # adjust if needed

            def get_market_id_from_slug(slug: str) -> dict:
                print(f"Fetching market ID for slug: {slug}")
                url = f"{API_BASE}/markets/slug/{slug}"
                resp = requests.get(url)
                resp.raise_for_status()
                data = resp.json()
                print(f"Received data: {data}")
                return data  # inspect it; it should contain condition_id, slug, outcomes, etc.
            print(f"Market slugs to subscribe: {markets}")
            markets = [get_market_id_from_slug(slug).get("conditionId") for slug in markets]
            print(f"Subscribing to market IDs: {markets}")
            await self.ws_client.subscribe(markets)
            
            # Start listening
            await self.ws_client.listen()
            
        except KeyboardInterrupt:
            logger.info("Shutting down gracefully...")
        except Exception as e:
            logger.error(f"Application error: {e}", exc_info=True)
        finally:
            await self.cleanup()
    
    async def cleanup(self) -> None:
        """Cleanup resources"""
        logger.info("Cleaning up resources...")
        await self.ws_client.disconnect()


async def main():
    """Application entry point"""
    app = PolymarketHunter()
    await app.start()


if __name__ == "__main__":
    asyncio.run(main())
