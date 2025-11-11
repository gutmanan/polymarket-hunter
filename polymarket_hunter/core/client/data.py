import asyncio
import os
from functools import lru_cache
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv
from web3 import Web3

from polymarket_hunter.constants import USDC_ADDRESS, USDC_ABI, USDC_DECIMALS, CTF_ADDRESS, CTF_ABI, ZERO_B32, \
    MAIN_EXCHANGE_ADDRESS, NEG_RISK_MARKETS_ADDRESS, NEG_RISK_ADAPTER_ADDRESS
from polymarket_hunter.utils.logger import setup_logger
from polymarket_hunter.utils.market import retryable, with_timeout

load_dotenv()
logger = setup_logger(__name__)


class DataClient:
    def __init__(self, timeout: int = 15.0):
        self.data_url = os.environ.get("DATA_HOST", "https://data-api.polymarket.com")
        self.polygon_rpc = os.getenv("RPC_URL")
        self.positions_endpoint = self.data_url + "/positions"
        self.closed_positions_endpoint = self.data_url + "/closed-positions"
        self.value_endpoint = self.data_url + "/value"
        self.trades_endpoint = self.data_url + "/trades"
        self._client = httpx.AsyncClient(timeout=timeout)

        self.private_key = os.getenv("PRIVATE_KEY")

        if not self.private_key:
            raise RuntimeError("Missing PRIVATE_KEY in env")

        # web3 (for approvals/balances; PoA middleware for Polygon)
        self.w3 = Web3(Web3.HTTPProvider(self.polygon_rpc))
        self.account = self.w3.eth.account.from_key(self.private_key)
        self.address = self.account.address

    # ---------- user-scoped reads ----------

    async def get_positions(self, user: str = None, querystring_params: Optional[Dict[str, Any]] = None) -> Any:
        params = dict(querystring_params or {})
        addr = user or self.address
        params["user"] = addr

        try:
            response = await self._client.get(self.positions_endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            logger.warning("Positions request timed out for %s", addr)
            return {"error": "timeout", "user": addr}
        except httpx.ConnectError as e:
            logger.error("Connection error getting positions for %s: %s", addr, e)
            return {"error": "connection_failed", "user": addr, "details": str(e)}
        except httpx.HTTPStatusError as e:
            logger.warning("Bad status %s for positions(%s): %s", e.response.status_code, addr, e)
            return {"error": "bad_status", "status_code": e.response.status_code, "text": e.response.text}
        except Exception as e:
            logger.exception("Unexpected error getting positions for %s", addr)
            return {"error": "unexpected", "details": str(e)}

    async def get_closed_positions(self, user: str = None, querystring_params: Optional[Dict[str, Any]] = None) -> Any:
        params = dict(querystring_params or {})
        addr = user if user is not None else self.address
        params["user"] = addr

        if "since" in params:
            params.setdefault("from", params["since"])  # some deployments
            params.setdefault("start", params["since"])  # legacy
        if "until" in params:
            params.setdefault("to", params["until"])  # some deployments
            params.setdefault("end", params["until"])  # legacy

        response = await self._client.get(self.closed_positions_endpoint, params=params)
        response.raise_for_status()
        return response.json()

    async def get_portfolio_value(self, user: str = None) -> list[dict[str, float]]:
        params = dict({})
        addr = user if user is not None else self.address
        params["user"] = addr

        response = await self._client.get(self.value_endpoint, params=params)
        response.raise_for_status()
        return response.json()

    # ---------- wallet actions ----------

    def get_usdc_balance(self, user: str = None) -> float:
        usdc = self.w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI)
        user_account = Web3.to_checksum_address(user if user is not None else self.address)
        balance = usdc.functions.balanceOf(user_account).call()
        return balance / 10 ** USDC_DECIMALS

    def get_usdc_allowance(self, user: str = None):
        user_address = Web3.to_checksum_address(user if user is not None else self.address)
        usdc = self.w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI)
        allowances = {}
        for index, address in enumerate([MAIN_EXCHANGE_ADDRESS, NEG_RISK_MARKETS_ADDRESS, NEG_RISK_ADAPTER_ADDRESS]):
            address_cksum = Web3.to_checksum_address(address)
            allowance = usdc.functions.allowance(user_address, address_cksum).call()
            allowances[index] = allowance
        return allowances

    def split_position(self, condition_id: str, partition: list[int] = [1, 2], amount_wei: int = 0) -> str:
        """
        Mint outcome tokens (complete sets) by splitting collateral into outcomes.
        - condition_id: bytes32 hex string for the market's condition
        - partition: list of index sets (binary default [1,2])
        - amount_wei: how many *complete sets* to mint, in USDC wei (6 decimals)
                      e.g. 1 USDC == 1_000_000
        """
        ctf = self.w3.eth.contract(address=CTF_ADDRESS, abi=CTF_ABI)
        tx = ctf.functions.splitPosition(
            Web3.to_checksum_address(USDC_ADDRESS),  # collateralToken
            ZERO_B32,  # parentCollectionId (top-level)
            Web3.to_bytes(hexstr=condition_id),  # conditionId
            partition,  # index sets (e.g., [1,2])
            int(amount_wei)  # amount (complete sets)
        ).buildTransaction({
            "from": self.address,
            "nonce": self.w3.eth.get_transaction_count(self.address),
            "gasPrice": self.w3.eth.gas_price,
        })
        tx["gas"] = self.w3.eth.estimate_gas(tx)
        signed = self.account.sign_transaction(tx)
        h = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return h.hex()

    def merge_position(self, condition_id: str, partition: list[int] = [1, 2], amount_wei: int = 0) -> str:
        """
        Burn equal amounts of each outcome and receive collateral back.
        - amount_wei must be <= min(balance(YES), balance(NO)) for this condition.
        """
        ctf = self.w3.eth.contract(address=CTF_ADDRESS, abi=CTF_ABI)
        tx = ctf.functions.mergePositions(
            Web3.to_checksum_address(USDC_ADDRESS),  # collateralToken
            ZERO_B32,  # parentCollectionId (top-level)
            Web3.to_bytes(hexstr=condition_id),  # conditionId
            partition,  # index sets (e.g., [1,2])
            int(amount_wei)  # amount to merge (complete sets)
        ).buildTransaction({
            "from": self.address,
            "nonce": self.w3.eth.get_transaction_count(self.address),
            "gasPrice": self.w3.eth.gas_price,
        })
        tx["gas"] = self.w3.eth.estimate_gas(tx)
        signed = self.account.sign_transaction(tx)
        h = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return h.hex()

    @retryable()
    async def redeem_position_async(self, condition_id: str):
        return await with_timeout(asyncio.to_thread(self.redeem_position, condition_id), 10)

    def redeem_position(self, condition_id: str, partition: list[int] = [1, 2]) -> str:
        """
        Redeem market positions.
        - condition_id: bytes32 hex string for the condition
        - partition: list of index sets (binary default [1,2])
        """
        ctf = self.w3.eth.contract(address=CTF_ADDRESS, abi=CTF_ABI)
        tx = ctf.functions.redeemPositions(
            Web3.to_checksum_address(USDC_ADDRESS),
            ZERO_B32,
            Web3.to_bytes(hexstr=condition_id),
            partition
        ).build_transaction({
            "from": self.address,
            "nonce": self.w3.eth.get_transaction_count(self.address),
            "gasPrice": self.w3.eth.gas_price,
        })
        tx["gas"] = self.w3.eth.estimate_gas(tx)
        signed = self.account.sign_transaction(tx)
        h = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return h.hex()

    async def is_market_resolved(self, condition_id: str) -> bool:
        try:
            ctf = self.w3.eth.contract(address=CTF_ADDRESS, abi=CTF_ABI)
            denom = ctf.functions.payoutDenominator(condition_id).call()
            return int(denom) > 0
        except Exception as e:
            logger.error("CTF check failed for %s: %s", condition_id, e)
            return False


@lru_cache(maxsize=1)
def get_data_client() -> DataClient:
    return DataClient()


if __name__ == "__main__":
    client = DataClient()
    print(client.redeem_position("0x999656aed064d6f1c5fc80b9400b20486c0abf3773d8286aaec215e5080f6ba8"))
    print(client.get_portfolio_value())
