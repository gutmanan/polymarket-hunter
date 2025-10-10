import asyncio
import json
import websockets
from typing import Callable, Optional, Dict, Any
from src.utils.logger import setup_logger
from src.config.settings import settings

logger = setup_logger(__name__)


class PolymarketWebSocket:
    """WebSocket client for Polymarket real-time data"""
    
    def __init__(self, url: Optional[str] = None):
        self.url = url or settings.POLYMARKET_WS_URL
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.is_connected = False
        self.message_handlers: list[Callable] = []
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 5
        
    async def connect(self) -> None:
        """Establish WebSocket connection"""
        try:
            logger.info(f"Connecting to Polymarket WebSocket: {self.url}")
            self.ws = await websockets.connect(
                self.url,
                ping_interval=20,
                ping_timeout=10
            )
            self.is_connected = True
            self._reconnect_attempts = 0
            logger.info("Successfully connected to Polymarket WebSocket")
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket: {e}")
            raise
    
    async def disconnect(self) -> None:
        """Close WebSocket connection"""
        if self.ws:
            await self.ws.close()
            self.is_connected = False
            logger.info("Disconnected from Polymarket WebSocket")
    
    async def subscribe(self, market_ids: list[str]) -> None:
        """Subscribe to specific market updates"""
        if not self.is_connected or not self.ws:
            raise ConnectionError("WebSocket not connected")
        
        subscription_message = {
            "type": "subscribe",
            "markets": market_ids
        }
        
        await self.ws.send(json.dumps(subscription_message))
        logger.info(f"Subscribed to {len(market_ids)} markets")
    
    def add_handler(self, handler: Callable[[Dict[Any, Any]], None]) -> None:
        """Add a message handler"""
        self.message_handlers.append(handler)
    
    async def listen(self) -> None:
        """Listen for incoming messages"""
        if not self.is_connected or not self.ws:
            raise ConnectionError("WebSocket not connected")
        
        logger.info("Starting to listen for messages...")
        
        try:
            async for message in self.ws:
                try:
                    data = json.loads(message)
                    logger.debug(f"Received message: {data}")
                    
                    # Call all registered handlers
                    for handler in self.message_handlers:
                        try:
                            await handler(data)
                        except Exception as e:
                            logger.error(f"Handler error: {e}")
                            
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse message: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self.is_connected = False
            await self._reconnect()
    
    async def _reconnect(self) -> None:
        """Attempt to reconnect with exponential backoff"""
        if self._reconnect_attempts >= self._max_reconnect_attempts:
            logger.error("Max reconnection attempts reached")
            return
        
        self._reconnect_attempts += 1
        wait_time = min(2 ** self._reconnect_attempts, 60)
        logger.info(f"Reconnecting in {wait_time} seconds (attempt {self._reconnect_attempts})")
        
        await asyncio.sleep(wait_time)
        
        try:
            await self.connect()
            await self.listen()
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            await self._reconnect()
