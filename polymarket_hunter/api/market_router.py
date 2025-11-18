from fastapi import APIRouter, HTTPException

from polymarket_hunter.dal.slug_store import RedisSlugStore

router = APIRouter()
slug_store = RedisSlugStore()

@router.get("/slugs")
async def list_slugs():
    return {"slugs": await slug_store.list()}


@router.put("/slugs/{slug}")
async def add_slug(slug: str):
    if not slug:
        raise HTTPException(status_code=400, detail="slug is required")

    await slug_store.add(slug)
    return {"slug": slug, "slugs": sorted(await slug_store.list())}


@router.delete("/slugs/{slug}")
async def delete_slug(slug: str):
    if not slug:
        raise HTTPException(status_code=400, detail="slug is required")

    await slug_store.remove(slug)
    return {"slug": slug, "slugs": sorted(await slug_store.list())}
