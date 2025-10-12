from typing import Optional, Dict, Any

import requests


class ClobClient:
    """Client for interacting with Polymarket CLOB API"""
    
    def __init__(self):
        self.base_url = "https://clob.polymarket.com"
        self.prices_history_endpoint = f"{self.base_url}/prices-history"

    def get_price_history(
        self,
        market: str,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        interval: Optional[str] = None,
        fidelity: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Get price history for a traded token.
        Fetches historical price data for a specified market token.
        
        Args:
            market (str): The CLOB token ID for which to fetch price history
            start_ts (Optional[int]): The start time, a Unix timestamp in UTC
            end_ts (Optional[int]): The end time, a Unix timestamp in UTC
            interval (Optional[str]): A string representing a duration ending at the current time.
                                     Mutually exclusive with start_ts and end_ts
            fidelity (Optional[int]): The resolution of the data, in minutes
        
        Returns:
            Dict[str, Any]: The price history data response
            
        Raises:
            ValueError: If both interval and (start_ts/end_ts) are provided
            requests.RequestException: If the API request fails
        """
        # Validate mutually exclusive parameters
        if interval and (start_ts is not None or end_ts is not None):
            raise ValueError("interval is mutually exclusive with start_ts and end_ts")
        
        # Build query parameters
        params = {"market": market}
        
        if interval:
            params["interval"] = interval
        else:
            if start_ts is not None:
                params["startTs"] = start_ts
            if end_ts is not None:
                params["endTs"] = end_ts
        
        if fidelity is not None:
            params["fidelity"] = fidelity
        
        # Make the API request
        try:
            print(f"Fetching price history with params: {params}, {self.prices_history_endpoint}")
            response = requests.get(self.prices_history_endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            raise requests.RequestException(f"Error fetching price history for market {market}: {e}")