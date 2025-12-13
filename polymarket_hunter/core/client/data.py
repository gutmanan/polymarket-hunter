from functools import lru_cache
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv
from web3 import Web3, AsyncWeb3

from polymarket_hunter.config.settings import settings
from polymarket_hunter.constants import USDC_ADDRESS, USDC_ABI, USDC_DECIMALS, CTF_ADDRESS, CTF_ABI, ZERO_B32, \
    MAIN_EXCHANGE_ADDRESS, NEG_RISK_MARKETS_ADDRESS, NEG_RISK_ADAPTER_ADDRESS
from polymarket_hunter.utils.logger import setup_logger

load_dotenv()
logger = setup_logger(__name__)

MAX_AMOUNT = 2 ** 256 - 1

class DataClient:
    def __init__(self, timeout: int = 15.0):
        self.data_url = settings.DATA_HOST
        self.polygon_rpc = settings.RPC_URL
        self.positions_endpoint = self.data_url + "/positions"
        self.closed_positions_endpoint = self.data_url + "/closed-positions"
        self.value_endpoint = self.data_url + "/value"
        self.trades_endpoint = self.data_url + "/trades"
        self._client = httpx.AsyncClient(timeout=timeout)

        self.private_key = settings.PRIVATE_KEY

        if not self.private_key:
            raise RuntimeError("Missing PRIVATE_KEY in env")

        # web3 (for approvals/balances; PoA middleware for Polygon)
        self.w3 = AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(self.polygon_rpc))
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
            logger.error("Positions request timed out for %s", addr)
            return {"error": "timeout", "user": addr}
        except httpx.ConnectError as e:
            logger.error("Connection error getting positions for %s: %s", addr, e)
            return {"error": "connection_failed", "user": addr, "details": str(e)}
        except httpx.HTTPStatusError as e:
            logger.error("Bad status %s for positions(%s): %s", e.response.status_code, addr, e)
            return {"error": "bad_status", "status_code": e.response.status_code, "text": e.response.text}
        except Exception as e:
            logger.error("Unexpected error getting positions for %s", addr)
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

    async def get_usdc_balance(self, user: str = None) -> float:
        usdc = self.w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI)
        user_account = Web3.to_checksum_address(user if user is not None else self.address)
        balance = await usdc.functions.balanceOf(user_account).call()
        return balance / 10 ** USDC_DECIMALS

    async def get_usdc_allowance(self, user: str = None):
        user_address = Web3.to_checksum_address(user if user is not None else self.address)
        usdc = self.w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI)
        allowances = {}
        for index, address in enumerate([MAIN_EXCHANGE_ADDRESS, NEG_RISK_MARKETS_ADDRESS, NEG_RISK_ADAPTER_ADDRESS]):
            address_cksum = Web3.to_checksum_address(address)
            allowance = await usdc.functions.allowance(user_address, address_cksum).call()
            allowances[index] = allowance
        return allowances

    async def approve_usdc(self, user: str = None):
        user_address = Web3.to_checksum_address(user if user is not None else self.address)
        usdc = self.w3.eth.contract(address=Web3.to_checksum_address(USDC_ADDRESS), abi=USDC_ABI)

        spenders = [MAIN_EXCHANGE_ADDRESS, NEG_RISK_MARKETS_ADDRESS, NEG_RISK_ADAPTER_ADDRESS]

        for spender in spenders:
            spender_cksum = Web3.to_checksum_address(spender)
            current_allowance = await usdc.functions.allowance(user_address, spender_cksum).call()
            if current_allowance == 0:
                logger.info(f"Approving {spender}...")
                nonce = await self.w3.eth.get_transaction_count(user_address)
                gas_price = await self.w3.eth.gas_price

                tx = await usdc.functions.approve(
                    spender_cksum,
                    MAX_AMOUNT
                ).build_transaction({
                    'from': user_address,
                    'nonce': nonce,
                    'gasPrice': gas_price
                })

                tx["gas"] = await self.w3.eth.estimate_gas(tx)
                signed = self.account.sign_transaction(tx)
                h = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
                receipt = await self.w3.eth.wait_for_transaction_receipt(h)
                logger.info(f"Approved {spender}. Hash: {receipt['transactionHash'].hex()}")

    async def split_position(self, condition_id: str, partition=None, amount_wei: int = 0) -> str:
        """
        Mint outcome tokens (complete sets) by splitting collateral into outcomes.
        - condition_id: bytes32 hex string for the market's condition
        - partition: list of index sets (binary default [1,2])
        - amount_wei: how many *complete sets* to mint, in USDC wei (6 decimals)
                      e.g. 1 USDC == 1_000_000
        """
        if partition is None:
            partition = [1, 2]

        ctf = self.w3.eth.contract(address=Web3.to_checksum_address(CTF_ADDRESS), abi=CTF_ABI)
        nonce = await self.w3.eth.get_transaction_count(self.address)
        gas_price = await self.w3.eth.gas_price

        tx = await ctf.functions.splitPosition(
            Web3.to_checksum_address(USDC_ADDRESS),  # collateralToken
            ZERO_B32,  # parentCollectionId (top-level)
            Web3.to_bytes(hexstr=condition_id),  # conditionId
            partition,  # index sets (e.g., [1,2])
            int(amount_wei)  # amount (complete sets)
        ).build_transaction({
            "from": self.address,
            "nonce": nonce,
            "gasPrice": gas_price
        })
        tx["gas"] = await self.w3.eth.estimate_gas(tx)
        signed = self.account.sign_transaction(tx)
        h = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return h.hex()

    async def merge_position(self, condition_id: str, partition=None, amount_wei: int = 0) -> str:
        """
        Burn equal amounts of each outcome and receive collateral back.
        - amount_wei must be <= min(balance(YES), balance(NO)) for this condition.
        """
        if partition is None:
            partition = [1, 2]

        ctf = self.w3.eth.contract(address=Web3.to_checksum_address(CTF_ADDRESS), abi=CTF_ABI)
        nonce = await self.w3.eth.get_transaction_count(self.address)
        gas_price = await self.w3.eth.gas_price

        tx = await ctf.functions.mergePositions(
            Web3.to_checksum_address(USDC_ADDRESS),  # collateralToken
            ZERO_B32,  # parentCollectionId (top-level)
            Web3.to_bytes(hexstr=condition_id),  # conditionId
            partition,  # index sets (e.g., [1,2])
            int(amount_wei)  # amount to merge (complete sets)
        ).build_transaction({
            "from": self.address,
            "nonce": nonce,
            "gasPrice": gas_price
        })
        tx["gas"] = await self.w3.eth.estimate_gas(tx)
        signed = self.account.sign_transaction(tx)
        h = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return h.hex()

    async def redeem_position(self, condition_id: str, partition=None) -> str:
        """
        Redeem market positions asynchronously.
        - condition_id: bytes32 hex string for the condition
        - partition: list of index sets (binary default [1,2])
        """
        if partition is None:
            partition = [1, 2]

        ctf = self.w3.eth.contract(address=Web3.to_checksum_address(CTF_ADDRESS), abi=CTF_ABI)
        nonce = await self.w3.eth.get_transaction_count(self.address)
        gas_price = await self.w3.eth.gas_price

        tx = await ctf.functions.redeemPositions(
            Web3.to_checksum_address(USDC_ADDRESS),
            ZERO_B32,
            Web3.to_bytes(hexstr=condition_id),
            partition
        ).build_transaction({
            "from": self.address,
            "nonce": nonce,
            "gasPrice": gas_price,
        })
        tx["gas"] = await self.w3.eth.estimate_gas(tx)
        signed = self.account.sign_transaction(tx)
        h = await self.w3.eth.send_raw_transaction(signed.raw_transaction)
        return h.hex()

    async def is_market_resolved(self, condition_id: str) -> bool:
        try:
            ctf = self.w3.eth.contract(address=Web3.to_checksum_address(CTF_ADDRESS), abi=CTF_ABI)
            denominator = await ctf.functions.payoutDenominator(condition_id).call()
            return int(denominator) > 0
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
