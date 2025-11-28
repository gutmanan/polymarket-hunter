import json

from fastapi import APIRouter

from polymarket_hunter.core.client.data import get_data_client

router = APIRouter()
data = get_data_client()


@router.get("/user_portfolio")
async def get_user_portfolio():
    usdc = await data.get_usdc_balance()
    portfolio = await data.get_portfolio_value()
    total_value = float(portfolio[0]["value"] if portfolio else 0)
    return {
        "cash": usdc,
        "portfolio": total_value
    }
