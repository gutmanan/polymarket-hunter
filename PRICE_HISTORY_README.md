# Price History API

This module provides functionality to fetch historical price data for Polymarket tokens using the CLOB API.

## Overview

The price history functionality is implemented in two layers:

1. **ClobClient** (`src/client/clob_client.py`): A reusable client for the Polymarket CLOB API
2. **fetch_asset_price_history** (`history/main.py`): A convenience function that uses the ClobClient

## Usage

### Basic Usage

```python
from history.main import fetch_asset_price_history

# Fetch last 24 hours with 1-hour intervals
history = fetch_asset_price_history(
    market="your_clob_token_id",
    interval="1d",
    fidelity=60
)

# Fetch specific time range
import time
end_time = int(time.time())
start_time = end_time - (7 * 24 * 60 * 60)  # 7 days ago

history = fetch_asset_price_history(
    market="your_clob_token_id",
    start_ts=start_time,
    end_ts=end_time,
    fidelity=240  # 4-hour intervals
)
```

### Using ClobClient Directly

```python
from src.client.clob_client import ClobClient

client = ClobClient()
history = client.get_price_history(
    market="your_clob_token_id",
    interval="7d",
    fidelity=360  # 6-hour intervals
)
```

## API Parameters

### Required
- **market** (string): The CLOB token ID for which to fetch price history

### Optional
- **start_ts** (number): Start time as Unix timestamp in UTC
- **end_ts** (number): End time as Unix timestamp in UTC  
- **interval** (string): Duration ending at current time (mutually exclusive with start_ts/end_ts)
- **fidelity** (number): Resolution of data in minutes

### Valid Interval Values
Common interval values include:
- `"1h"` - Last hour
- `"1d"` - Last day
- `"7d"` - Last week
- `"30d"` - Last month

## Validation Rules

- `interval` and `start_ts`/`end_ts` are mutually exclusive
- If using time range, you can specify either or both of `start_ts` and `end_ts`
- All timestamps should be Unix timestamps in UTC

## Error Handling

The functions will raise:
- `ValueError`: For invalid parameter combinations
- `requests.RequestException`: For API request failures

## Examples

### Example 1: Recent Price Data
```python
# Get last 24 hours of price data with 30-minute intervals
recent_prices = fetch_asset_price_history(
    market="34162837781730672011660772212644013215160907668136521982857571151824030405052",
    interval="1d",
    fidelity=30
)
```

### Example 2: Historical Range
```python
import time

# Get price data from one week ago to now
now = int(time.time())
week_ago = now - (7 * 24 * 60 * 60)

weekly_prices = fetch_asset_price_history(
    market="34162837781730672011660772212644013215160907668136521982857571151824030405052",
    start_ts=week_ago,
    end_ts=now,
    fidelity=120  # 2-hour intervals
)
```

### Example 3: High-Resolution Recent Data
```python
# Get last 6 hours with 5-minute resolution
high_res_prices = fetch_asset_price_history(
    market="34162837781730672011660772212644013215160907668136521982857571151824030405052",
    interval="6h", 
    fidelity=5
)
```

## Running the Examples

To run the example in `history/main.py`:

```bash
cd /path/to/polymarket-hunter
PYTHONPATH=. python history/main.py
```

To run the tests:

```bash
cd /path/to/polymarket-hunter  
python test_price_history.py
```