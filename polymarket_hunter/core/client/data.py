import os
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv
from web3 import Web3

from polymarket_hunter.constants import USDC_ADDRESS, USDC_ABI, USDC_DECIMALS, CTF_ADDRESS, CTF_ABI, ZERO_B32

load_dotenv()


class DataClient:
    def __init__(
            self,
            polygon_rpc: str = os.getenv("RPC_URL"),
    ):
        self.data_url = os.environ.get("DATA_HOST", "https://data-api.polymarket.com")
        self.positions_endpoint = self.data_url + "/positions"
        self.closed_positions_endpoint = self.data_url + "/closed-positions"
        self.value_endpoint = self.data_url + "/value"
        self.trades_endpoint = self.data_url + "/trades"

        self.private_key = os.getenv("PRIVATE_KEY")
        if not self.private_key:
            raise RuntimeError("Missing PRIVATE_KEY in env")

        # web3 (for approvals/balances; PoA middleware for Polygon)
        self.w3 = Web3(Web3.HTTPProvider(polygon_rpc))
        self.account = self.w3.eth.account.from_key(self.private_key)
        self.address = self.account.address

    # ---------- user-scoped reads ----------

    def get_positions(self, user: str = None, querystring_params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Current (open) positions for the wallet/user.
        NOTE: If you trade via a funder/proxy, pass the *funder* address here.
        """
        params = dict(querystring_params or {})
        params["user"] = user if user is not None else self.address
        response = httpx.get(self.positions_endpoint, params=params)
        return response.json()

    def get_closed_positions(self, user: str, querystring_params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Closed positions (resolved/settled) with realized PnL, etc.
        """
        params = dict(querystring_params or {})
        params["user"] = user if user is not None else self.address
        response = httpx.get(self.closed_positions_endpoint, params=params)
        return response.json()

    def get_portfolio_value(self, user: str) -> Any:
        """
        Aggregated wallet value: totalValue, cash, unsettled, pnl, etc.
        """
        response = httpx.get(self.value_endpoint, params={"user": user if user is not None else self.address})
        return response.json()

    def get_usdc_balance(self, user: str) -> float:
        """
        USDC balance (Polygon).
        """

        usdc = self.w3.eth.contract(address=USDC_ADDRESS, abi=USDC_ABI)
        raw = usdc.functions.balanceOf(user if user is not None else self.address).call()
        return raw / 10 ** USDC_DECIMALS

    def get_trades(self, user: str, querystring_params: Optional[Dict[str, Any]] = None) -> Any:
        """
        User trades/fills. Optional filters can include:
        - limit, cursor
        - since, until (epoch seconds)
        - market (market_id), token_id
        """
        params = dict(querystring_params or {})
        params["user"] = user if user is not None else self.address
        response = httpx.get(self.trades_endpoint, params=params)
        return response.json()

    # ---------- wallet actions ----------

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
            Web3.toChecksumAddress(USDC_ADDRESS),  # collateralToken
            ZERO_B32,  # parentCollectionId (top-level)
            Web3.toBytes(hexstr=condition_id),  # conditionId
            partition,  # index sets (e.g., [1,2])
            int(amount_wei)  # amount (complete sets)
        ).buildTransaction({
            "from": self.address,
            "nonce": self.w3.eth.get_transaction_count(self.address),
            "gasPrice": self.w3.eth.gas_price,
        })
        tx["gas"] = self.w3.eth.estimate_gas(tx)
        signed = self.account.sign_transaction(tx)
        h = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        return h.hex()

    def merge_position(self, condition_id: str, partition: list[int] = [1, 2], amount_wei: int = 0) -> str:
        """
        Burn equal amounts of each outcome and receive collateral back.
        - amount_wei must be <= min(balance(YES), balance(NO)) for this condition.
        """
        ctf = self.w3.eth.contract(address=CTF_ADDRESS, abi=CTF_ABI)

        tx = ctf.functions.mergePositions(
            Web3.toChecksumAddress(USDC_ADDRESS),  # collateralToken
            ZERO_B32,  # parentCollectionId (top-level)
            Web3.toBytes(hexstr=condition_id),  # conditionId
            partition,  # index sets (e.g., [1,2])
            int(amount_wei)  # amount to merge (complete sets)
        ).buildTransaction({
            "from": self.address,
            "nonce": self.w3.eth.get_transaction_count(self.address),
            "gasPrice": self.w3.eth.gas_price,
        })
        tx["gas"] = self.w3.eth.estimate_gas(tx)
        signed = self.account.sign_transaction(tx)
        h = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        return h.hex()

    def redeem_position(self, condition_id: str, partition: list[int] = [1, 2]) -> str:
        ctf = self.w3.eth.contract(address=CTF_ADDRESS, abi=CTF_ABI)

        tx = ctf.functions.redeemPositions(
            Web3.toChecksumAddress(USDC_ADDRESS),
            ZERO_B32,
            Web3.toBytes(hexstr=condition_id),
            partition
        ).buildTransaction({
            "from": self.address,
            "nonce": self.w3.eth.get_transaction_count(self.address),
            "gasPrice": self.w3.eth.gas_price,
        })
        tx["gas"] = self.w3.eth.estimate_gas(tx)
        signed = self.account.sign_transaction(tx)
        h = self.w3.eth.send_raw_transaction(signed.rawTransaction)
        return h.hex()


if __name__ == "__main__":
    client = DataClient()
    res = client.redeem_position(
        "0xb4fa147809056e536d389de096d260d46956985fa12424c855f88482b2c13122",
        [1, 2]
    )
    print(res)
