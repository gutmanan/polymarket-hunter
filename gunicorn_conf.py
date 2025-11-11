import multiprocessing
import os

# Basic polymarket_hunter settings
bind = os.getenv("BIND", "0.0.0.0:8080")
workers = int(os.getenv("WORKERS", multiprocessing.cpu_count() * 2 + 1))
worker_class = "uvicorn.workers.UvicornWorker"

# Concurrency and performance
threads = int(os.getenv("THREADS", 2))
worker_connections = int(os.getenv("WORKER_CONNECTIONS", 1000))

# Timeouts
timeout = int(os.getenv("TIMEOUT", 30))
graceful_timeout = int(os.getenv("GRACEFUL_TIMEOUT", 30))
keepalive = int(os.getenv("KEEPALIVE", 5))

# Logging
accesslog = "-"   # stdout
errorlog = "-"    # stderr
loglevel = os.getenv("LOG_LEVEL", "info")

# Preload polymarket_hunter for faster startup (only if your polymarket_hunter is stateless)
preload_app = True

# Optional: tweak Uvicorn settings
forwarded_allow_ips = "*"
proxy_allow_ips = "*"

# Optional: lifecycle hooks
def on_starting(server):
    server.log.info(f"🚀 Starting Gunicorn with {workers} workers, {threads} threads")

def when_ready(server):
    server.log.info("✅ Gunicorn workers are ready to serve requests")

def worker_exit(server, worker):
    server.log.info(f"💤 Worker {worker.pid} exited")
