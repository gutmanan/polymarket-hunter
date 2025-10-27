import asyncio
import os

from dotenv import load_dotenv
from telegram import Bot
from telegram.constants import ParseMode

from polymarket_hunter.utils.logger import setup_logger

load_dotenv()
logger = setup_logger(__name__)

class TelegramNotifier:

    def __init__(self):
        self.telegram_bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        self.bot = Bot(token=self.telegram_bot_token)

    async def send_message(self, message):
        try:
            await self.bot.send_message(
                chat_id=self.telegram_chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=False
            )
        except Exception as e:
            logger.error(f"Error sending message: {e}")

if __name__ == "__main__":
    notifier = TelegramNotifier()
    asyncio.run(notifier.send_message("hello"))
