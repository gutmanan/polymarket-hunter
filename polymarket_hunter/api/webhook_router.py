from typing import Dict

from fastapi import APIRouter, Header, HTTPException

router = APIRouter()


@router.post("/webhook")
async def webhook(payload: Dict, x_api_key: str | None = Header(default=None)):
    action = (payload.get("action") or "").lower()
    if action not in {"pause", "resume", "boost"}:
        raise HTTPException(status_code=400, detail="invalid action")
    # Placeholder for future behavior
    return {"ok": True, "action": action}
