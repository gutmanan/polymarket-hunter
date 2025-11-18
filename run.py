import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        app="polymarket_hunter.main:app",
        host="0.0.0.0",
        port=8080,
        env_file=".env",
        reload=True,
        reload_dirs=["polymarket_hunter"],
        log_level="info"
    )
else:
    from polymarket_hunter.main import app
