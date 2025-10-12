from concurrent.futures import ProcessPoolExecutor
import json
from pathlib import Path
from typing import Optional, Union, Dict, Any
import time

from src.client.gamma_client import GammaClient
from src.client.clob_client import ClobClient


def fetch_asset_price_history(
    market: str,
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
    interval: Optional[str] = None,
    fidelity: Optional[int] = None
) -> Dict[str, Any]:
    """
    Get price history for a traded token using the ClobClient.
    
    Args:
        market (str): The CLOB token ID for which to fetch price history
        start_ts (Optional[int]): The start time, a Unix timestamp in UTC
        end_ts (Optional[int]): The end time, a Unix timestamp in UTC
        interval (Optional[str]): A string representing a duration ending at the current time.
                                 Mutually exclusive with start_ts and end_ts
        fidelity (Optional[int]): The resolution of the data, in minutes
    
    Returns:
        Dict[str, Any]: The price history data response
    """
    clob_client = ClobClient()
    price_history = clob_client.get_price_history(
        market=market,
        start_ts=start_ts,
        end_ts=end_ts,
        interval=interval,
        fidelity=fidelity
    )
    print(f"Total: {len(price_history.get('history', []))} data points fetched")
    return price_history


def is_asset_volatile(prices: dict, prime_percentage: float, lower_threshold: float):
    """
    Determines if an asset reached prime percentage and then to lower threshold
    """
    logged_timestamps = []
    peak_reached = False
    print("Received prices:", prices)
    for price in prices[1:]:
        if not peak_reached:
            if price["p"] >= prime_percentage:
                peak_reached = True
                logged_timestamps.append(price["t"])
        else:
            if price["p"] <= lower_threshold:
                logged_timestamps.append(price["t"])
                return True, logged_timestamps

    return False, logged_timestamps

def is_asset_resolved_after_peak(market: dict):
    """
    Determines if an asset reached prime percentage and then resolved
    """
    logged_timestamps = []
    prime_percentage = 0.9
    peak_reached = False
    resolved_after_peak = False
    history_1 = fetch_asset_price_history(
        market=json.loads(market.get("clobTokenIds"))[0],
        interval="1m",
        fidelity=10
    )["history"]

    for price in history_1:
        if not peak_reached:
            if price["p"] >= prime_percentage:
                peak_reached = True
                logged_timestamps.append(price["t"])
        else:
            if price["p"] >= 0.99:
                logged_timestamps.append(price["t"])
                resolved_after_peak = True
                break

    market.update({"history": history_1, "resolved_after_peak": resolved_after_peak, "logged_timestamps": logged_timestamps})
    return market



if __name__ == "__main__":
    json_file = Path(__file__).parent / "api-response.json"
    with open(json_file, "r") as f:
        api_response = json.loads(f.read())
    
    gamma = GammaClient()
    csv_s = "slug,volatile,timestamps,data_points\n"
    number_of_markets = 100  # len(api_response)
    hits = 0
    total = 0
    # Use subprocessing to parallelize this if needed
    chunk_start = 0
    # Use ProcessPoolExecutor as a context manager
    all_results = []
    for chunk in range(number_of_markets // 100):
        chunk_start = chunk * 100
        chunk_end = chunk_start + 100
        # max_workers can be set to the number of CPU cores for optimal performance
        with ProcessPoolExecutor(max_workers=2) as executor:
            print("Starting parallel processing with map...")
            # Use executor.map to apply square_number to each item in numbers_to_process
            # The results are returned in the order of the input iterable
            results = executor.map(is_asset_resolved_after_peak, api_response[chunk_start:chunk_end])
            all_results.extend(results)
        
        print("Sleeping for 10 seconds...")
        time.sleep(10)

    for market in all_results:
        if not market.get("logged_timestamps"):
            continue
        if not market.get("history"):
            number_of_markets -= 1
            continue
        total += 1
        if market.get("resolved_after_peak"):
            hits += 1
        csv_s += f"{market['slug']},{market['resolved_after_peak']},{market['logged_timestamps']}\n"
        print(f"{market['slug']},{market['resolved_after_peak']},{market['logged_timestamps']}")

    print(number_of_markets, total, hits, hits / total if total > 0 else 0)
    with open("output.csv", "w") as f:
        f.write(csv_s)
    print("Wrote output.csv")
