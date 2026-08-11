from fastapi import APIRouter

from app.adapters.registry import get_adapter
from app.core.models import SearchRequest, SearchResponse
from app.db.persist import persist_scraped_jobs

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=SearchResponse)
async def search_jobs(req: SearchRequest):
    adapter = get_adapter(req.channel)
    jobs = await adapter.search(req)
    persist_scraped_jobs(jobs)
    return SearchResponse(
        jobs=jobs,
        total=len(jobs),
        page=req.page,
        channel=req.channel,
    )
