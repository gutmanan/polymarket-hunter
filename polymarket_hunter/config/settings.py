from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # Application
    APP_NAME: str = "Polymarket Hunter"
    APP_VERSION: str = "0.2.0"
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")
    LOG_FILE: str = Field(default="logs/polymarket_hunter.log", env="LOG_FILE")
    PORT: int = Field(default=8080, env="PORT")

    # Polymarket
    POLYMARKET_WS_URL: str = Field(default="wss://ws-subscriptions-clob.polymarket.com/ws", env="POLYMARKET_WS_URL")
    DATA_HOST: str = Field(default="https://data-api.polymarket.com", env="DATA_HOST")
    GAMMA_HOST: str = Field(default="https://gamma-api.polymarket.com", env="GAMMA_HOST")
    CLOB_HOST: str = Field(default="https://clob.polymarket.com", env="CLOB_HOST")
    RPC_URL: Optional[str] = Field(default="https://polygon-rpc.com", env="RPC_URL")

    # Wallet
    PRIVATE_KEY: Optional[str] = Field(default=None, env="PRIVATE_KEY")

    # Redis
    REDIS_URL: str = Field(default="redis://redis:6379/0", env="REDIS_URL")

    # Postgres
    POSTGRES_URL: str = Field(default="postgresql+asyncpg://admin:admin@postgres:5432/hunter", env="POSTGRES_URL")

    # Telegram
    TELEGRAM_BOT_TOKEN: Optional[str] = Field(default=None, env="TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID: Optional[str] = Field(default=None, env="TELEGRAM_CHAT_ID")

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
