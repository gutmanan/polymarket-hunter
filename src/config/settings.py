import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # Application
    APP_NAME: str = "Polymarket Hunter"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = Field(default=False, env="DEBUG")
    
    # Polymarket
    POLYMARKET_WS_URL: str = Field(
        default="wss://ws-subscriptions-clob.polymarket.com/ws/market",
        env="POLYMARKET_WS_URL"
    )
    POLYMARKET_API_KEY: Optional[str] = Field(default=None, env="POLYMARKET_API_KEY")
    POLYMARKET_PRIVATE_KEY: Optional[str] = Field(default=None, env="POLYMARKET_PRIVATE_KEY")
    
    # MCP Servers
    MCP_NEWS_SERVER: str = Field(default="http://localhost:3001", env="MCP_NEWS_SERVER")
    MCP_TWITTER_SERVER: str = Field(default="http://localhost:3002", env="MCP_TWITTER_SERVER")
    MCP_BINANCE_SERVER: str = Field(default="http://localhost:3003", env="MCP_BINANCE_SERVER")
    MCP_POLYMARKET_SERVER: str = Field(default="http://localhost:3004", env="MCP_POLYMARKET_SERVER")
    
    # Logging
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FILE: str = Field(default="logs/app.log", env="LOG_FILE")
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
