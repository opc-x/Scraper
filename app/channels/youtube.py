import logging

import httpx

from app.adapters.base import BaseAdapter
from app.core.channel_config import get_channel_config
from app.core.config import settings
from app.core.models import Job, SearchRequest
from app.infra import llm

logger = logging.getLogger(__name__)

YOUTUBE_SEARCH_API = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_API = "https://www.googleapis.com/youtube/v3/videos"


class YouTubeAdapter(BaseAdapter):
    """YouTube 官方 Data API v3 搜索：免费档 10000 units/day，search.list 每次 100 units，
    够用，不需要走浏览器/登录态那一套（跟 X 的处境完全不同，X 没有免费 API 才不得不用浏览器）。
    """

    name = "youtube"

    async def reload(self):
        pass

    async def search(self, req: SearchRequest) -> list[Job]:
        cfg = get_channel_config("youtube")
        api_key = cfg.get("api_key") or settings.youtube_api_key
        if not api_key:
            logger.warning("YouTube api_key 未配置")
            return []

        videos = await self._search_videos(req.keyword, api_key)
        if not videos:
            return []

        texts = [
            f"{v['title']} — {v['channel']}: {v['description']}".strip(" —:")
            for v in videos if v.get("title")
        ]
        return await llm.extract_jobs(cfg, texts, channel="youtube", id_prefix="yt")

    async def _search_videos(self, keyword: str, api_key: str) -> list[dict]:
        params = {
            "part": "snippet",
            "q": keyword,
            "type": "video",
            "maxResults": 20,
            "key": api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=15) as http:
                res = await http.get(YOUTUBE_SEARCH_API, params=params)
                if res.status_code != 200:
                    logger.error("YouTube search 失败 (%s): %s", res.status_code, res.text[:300])
                    return []
                videos = self.extract_videos(res.json())
                if not videos:
                    return []

                video_ids = ",".join(v["video_id"] for v in videos if v.get("video_id"))
                res2 = await http.get(
                    YOUTUBE_VIDEOS_API,
                    params={"part": "snippet", "id": video_ids, "key": api_key},
                )
                if res2.status_code == 200:
                    full_desc = {
                        item["id"]: item.get("snippet", {}).get("description", "")
                        for item in res2.json().get("items", [])
                    }
                    for v in videos:
                        if v["video_id"] in full_desc:
                            v["description"] = full_desc[v["video_id"]]
        except Exception as e:
            logger.error("YouTube search 请求异常: %s", e)
            return []

        return videos

    @staticmethod
    def extract_videos(data: dict) -> list[dict]:
        """从 search.list 响应里摘出视频的标题/频道/简介。"""
        videos = []
        for item in (data or {}).get("items", []):
            if item.get("id", {}).get("kind") != "youtube#video":
                continue
            snippet = item.get("snippet", {})
            videos.append({
                "video_id": item.get("id", {}).get("videoId", ""),
                "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""),
                "description": snippet.get("description", ""),
            })
        return videos

    async def close(self):
        pass
