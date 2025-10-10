from typing import Dict, Any
from src.utils.logger import setup_logger

logger = setup_logger(__name__)


class MessageHandler:
    """Handlers for different WebSocket message types"""
    
    @staticmethod
    async def handle_price_update(data: Dict[Any, Any]) -> None:
        """Handle price update messages"""
        if data.get("type") == "price_update":
            market_id = data.get("market_id")
            price = data.get("price")
            logger.info(f"Price update for market {market_id}: {price}")
            
    @staticmethod
    async def handle_volume_update(data: Dict[Any, Any]) -> None:
        """Handle volume update messages"""
        if data.get("type") == "volume_update":
            market_id = data.get("market_id")
            volume = data.get("volume")
            logger.info(f"Volume update for market {market_id}: {volume}")
            
    @staticmethod
    async def handle_market_creation(data: Dict[Any, Any]) -> None:
        """Handle new market creation messages"""
        if data.get("type") == "market_created":
            market_id = data.get("market_id")
            logger.info(f"New market created: {market_id}")
