from fastapi import APIRouter, HTTPException

from polymarket_hunter.dal.slug_store import RedisSlugStore

router = APIRouter(prefix="/market", tags=["Subscribed Markets"])
slug_store = RedisSlugStore()


@router.get("")
async def get():
    return {"slugs": await slug_store.list()}


@router.put("/{slug}")
async def add(slug: str):
    if not slug:
        raise HTTPException(status_code=400, detail="slug is required")

    await slug_store.add(slug)
    return {"slug": slug}


@router.delete("/{slug}")
async def remove(slug: str):
    if not slug:
        raise HTTPException(status_code=400, detail="slug is required")

    await slug_store.remove(slug)
    return {"slug": slug}
