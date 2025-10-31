from typing import Dict

from fastapi import APIRouter, HTTPException

from polymarket_hunter.dependencies.slugs_subscriber_dep import SlugsSubscriberDep

router = APIRouter()


@router.get("/slugs")
async def list_slugs(slugs_subscriber: SlugsSubscriberDep):
    slugs = sorted(list(slugs_subscriber.get_slugs()))
    return {"slugs": slugs}


@router.post("/slugs")
async def add_slug(payload: Dict[str, str], slugs_subscriber: SlugsSubscriberDep):
    slug = (payload.get("slug") or "").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="slug is required")
    # API key check is enforced via middleware in polymarket_hunter
    await slugs_subscriber.add_slug(slug)
    return {"slug": slug, "slugs": sorted(list(slugs_subscriber.get_slugs()))}


@router.delete("/slugs/{slug}")
async def delete_slug(slug: str, slugs_subscriber: SlugsSubscriberDep):
    await slugs_subscriber.remove_slug(slug)
    return {"slug": slug, "slugs": sorted(list(slugs_subscriber.get_slugs()))}
