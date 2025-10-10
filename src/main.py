import asyncio
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
