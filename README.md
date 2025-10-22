### Polymarket Hunter — Redis-backed dynamic hunter web server

This app exposes a minimal FastAPI control plane to manage a dynamic list of Polymarket market slugs ("hunter mode") and keeps shared state across replicas using Redis. It preserves the existing trading handlers and contracts.

Key endpoints:
- GET /healthz → {"status":"ok"}
- GET /slugs → {"slugs": [ ... ]}
- POST /slugs {"slug":"..."}
- DELETE /slugs/{slug}
- POST /webhook {"action":"pause|resume|boost"} (placeholder)

Environment (.env) — include these keys:

```
# Application Configuration
DEBUG=false
LOG_LEVEL=INFO
LOG_FILE=logs/app.log

# Polymarket Configuration
POLYMARKET_WS_URL=wss://ws-subscriptions-clob.polymarket.com/ws/market
DATA_HOST=https://data-api.polymarket.com
GAMMA_HOST=https://gamma-api.polymarket.com
CLOB_HOST=https://clob.polymarket.com
RPC_URL=https://polygon-rpc.com

# Required for wallet operations and order signing
PRIVATE_KEY=
POLYMARKET_API_KEY=
POLYMARKET_API_SECRET=
POLYMARKET_API_PASSPHRASE=

# New (for this app)
REDIS_URL=redis://redis:6379/0
PORT=8080
API_KEY=           # optional: if set, enforce X-API-Key auth
```

Run locally with Docker Compose:

- docker compose up --build
- Open http://localhost:8080/healthz

Scale to multiple replicas (state is shared via Redis):

- docker compose up --build --scale app=3

cURL examples:

- List slugs: curl -s http://localhost:8080/slugs
- Add slug: curl -s -X POST http://localhost:8080/slugs -H 'Content-Type: application/json' -d '{"slug":"bitcoin-up-or-down-october-21-3am-et"}'
- Remove slug: curl -s -X DELETE http://localhost:8080/slugs/bitcoin-up-or-down-october-21-3am-et

If API_KEY is set in .env, include: -H "X-API-Key: $API_KEY" with POST/DELETE requests.

Notes:
- The app keeps a single background WebSocket client per process and resubscribes when slugs change via Redis Pub/Sub.
- Existing handlers (MessageHandler, MessageContext, PriceChangeHandler, clob_client, data_client) remain intact.
