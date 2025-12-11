from prometheus_client import Counter, Gauge, Histogram

SLUG_RESOLUTION_LATENCY = Histogram(
    'ws_slug_resolution_duration_seconds',
    'Latency of resolving slugs to market data',
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, float('inf'))
)

CLIENT_UPTIME_SECONDS = Gauge(
    'ws_client_uptime_seconds',
    'Time since the WebSocket client started running'
)

MESSAGE_COUNT = Counter(
    'ws_messages_total',
    'Total incoming WebSocket messages',
    ['event_type']
)
