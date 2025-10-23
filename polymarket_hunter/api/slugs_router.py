from typing import Dict

from fastapi import APIRouter, HTTPException

from polymarket_hunter.dependencies.manager_dep import ManagerDep

router = APIRouter()


@router.get("/slugs")
async def list_slugs(manager: ManagerDep):
    slugs = sorted(list(manager.get_slugs()))
    return {"slugs": slugs}


@router.post("/slugs")
async def add_slug(payload: Dict[str, str], manager: ManagerDep):
    slug = (payload.get("slug") or "").strip()
    if not slug:
        raise HTTPException(status_code=400, detail="slug is required")
    # API key check is enforced via middleware in polymarket_hunter
    await manager.add_slug(slug)
    return {"slug": slug, "slugs": sorted(list(manager.get_slugs()))}


@router.delete("/slugs/{slug}")
async def delete_slug(slug: str, manager: ManagerDep):
    await manager.remove_slug(slug)
    return {"slug": slug, "slugs": sorted(list(manager.get_slugs()))}
