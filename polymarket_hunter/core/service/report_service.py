from __future__ import annotations

from decimal import Decimal

from polymarket_hunter.core.client.data import get_data_client
from polymarket_hunter.utils.logger import setup_logger

logger = setup_logger(__name__)

class ReportService:
    def __init__(self):
        self.data = get_data_client()

    # -------- Wallet value --------

    async def get_current_wallet_balance(self) -> Decimal:
        usdc = Decimal(str(self.data.get_usdc_balance() or 0))
        value = await self.data.get_portfolio_value()
        total_value = Decimal(str(value[0]["value"] or 0))
        return usdc + total_value

    # -------- Human summary --------

    async def generate_summary(self, *, hours_back: int) -> str:
        bal = await self.get_current_wallet_balance()
        return (
            f"📊 <b>Performance</b>\n"
            f"💼 Wallet (USDC + Portfolio): {bal}\n"
        )


if __name__ == "__main__":
    svc = ReportService()
    # sync-friendly usage (DataClient methods used here are sync)
    print(svc.generate_summary(hours_back=24))
