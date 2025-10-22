from typing import Dict

from fastapi import APIRouter, Depends, Header, HTTPException, status

from src.core.subscription_manager import SubscriptionManager

router = APIRouter()

# Dependency placeholder; actual injection will set get_manager in main
get_manager: SubscriptionManager | None = None  # will be overridden


def require_api_key(x_api_key: str | None = Header(default=None), api_key_required: bool = False, expected: str = ""):
    if not api_key_required:
        return
    if not expected:
        return
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")


@router.get("/slugs")
async def list_slugs(manager: SubscriptionManager = Depends(lambda: get_manager)):
    slugs = sorted(list(manager.get_slugs()))
    return {"slugs": slugs}


@router.post("/slugs")
async def add_slug(payload: Dict[str, str], manager: SubscriptionManager = Depends(lambda: get_manager), x_api_key: str | None = Header(default=None)):
    slug = (payload.get("slug") or "").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="slug is required")
    # API key check is enforced via middleware in app
    await manager.add_slug(slug)
    return {"slug": slug, "slugs": sorted(list(manager.get_slugs()))}


@router.delete("/slugs/{slug}")
async def delete_slug(slug: str, manager: SubscriptionManager = Depends(lambda: get_manager), x_api_key: str | None = Header(default=None)):
    await manager.remove_slug(slug)
    return {"slug": slug, "slugs": sorted(list(manager.get_slugs()))}
