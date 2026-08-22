import logging

import httpx
from fastapi import APIRouter, HTTPException

from app.core.channel_config import get_channel_config
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/drill", tags=["drill"])

YOUTUBE_SEARCH_API = "https://www.googleapis.com/youtube/v3/search"


def _api_key() -> str:
    cfg = get_channel_config("youtube")
    return cfg.get("api_key") or settings.youtube_api_key


@router.get("/search")
async def search_videos(q: str, page_token: str = "", max_results: int = 20):
    """英语面试实战素材搜索，直接走 YouTube 官方 Data API，不落库，纯代理搜索。"""
    api_key = _api_key()
    if not api_key:
        raise HTTPException(503, "未配置 YouTube API Key，去「渠道配置」→ YouTube 填一个")

    params = {
        "part": "snippet",
        "q": q,
        "type": "video",
        "maxResults": min(max(max_results, 1), 50),
        "relevanceLanguage": "en",
        "key": api_key,
    }
    if page_token:
        params["pageToken"] = page_token

    try:
        async with httpx.AsyncClient(timeout=15) as http:
            res = await http.get(YOUTUBE_SEARCH_API, params=params)
    except Exception as e:
        logger.error("drill search 请求异常: %s", e)
        raise HTTPException(502, f"请求 YouTube 失败：{e}")

    if res.status_code != 200:
        logger.error("drill search 失败 (%s): %s", res.status_code, res.text[:300])
        raise HTTPException(res.status_code, res.text[:300])

    data = res.json()
    items = []
    for item in data.get("items", []):
        if item.get("id", {}).get("kind") != "youtube#video":
            continue
        snippet = item.get("snippet", {})
        items.append({
            "id": item.get("id", {}).get("videoId", ""),
            "title": snippet.get("title", ""),
            "channel": snippet.get("channelTitle", ""),
            "description": snippet.get("description", ""),
            "thumbnail": (snippet.get("thumbnails", {}).get("medium") or {}).get("url", ""),
            "published_at": snippet.get("publishedAt", ""),
        })

    return {
        "videos": items,
        "next_page_token": data.get("nextPageToken", ""),
        "total_results": (data.get("pageInfo") or {}).get("totalResults", 0),
    }
