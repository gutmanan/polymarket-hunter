from __future__ import annotations

from polymarket_hunter.core.client.data import get_data_client
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)

class ReportService:
    def __init__(self):
        self.data = get_data_client()

    # ---------- utilities ----------

    async def _get_wallet_balance(self) -> float:
        usdc = await self.data.get_usdc_balance()
        portfolio = await self.data.get_portfolio_value()
        total_value = float(portfolio[0]["value"] if portfolio else 0)
        return usdc + total_value

    # ---------- public APIs ----------

    async def generate_summary(self, *, hours_back: int) -> str:
        bal = await self._get_wallet_balance()
        return (
            f"📊 <b>Performance</b>\n"
            f"💼 Wallet (USDC + Portfolio): {bal}\n"
        )
