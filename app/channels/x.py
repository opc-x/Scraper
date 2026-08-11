import asyncio
import json
import logging

from app.adapters.base import BaseAdapter
from app.core.channel_config import get_channel_config
from app.core.models import Job, SearchRequest
from app.infra import chrome, llm

logger = logging.getLogger(__name__)

SEARCH_API_PATTERN = "SearchTimeline"
X_SEARCH_URL = "https://x.com/search?q={query}&src=typed_query&f=live"


class XAdapter(BaseAdapter):
    """X（Twitter）全局搜索：抓帖子，用 LLM 从中提取招聘信息。"""

    name = "x"

    def __init__(self):
        self._page = None

    async def reload(self):
        await self.close()

    def _ensure_page(self):
        if self._page is None:
            self._page = chrome.new_page("x")
        cfg = get_channel_config("x")
        chrome.sync_cookies(self._page, "x", "https://x.com", ".x.com", cfg.get("cookie", ""))
        return self._page

    async def search(self, req: SearchRequest) -> list[Job]:
        posts = await asyncio.to_thread(self._search_posts_sync, req.keyword)
        if not posts:
            return []

        cfg = get_channel_config("x")
        texts = [f"@{p['screen_name']}: {p['text']}" for p in posts if p.get("text")]
        return await llm.extract_jobs(cfg, texts, channel="x", id_prefix="x")

    def _search_posts_sync(self, keyword: str) -> list[dict]:
        page = self._ensure_page()
        url = X_SEARCH_URL.format(query=keyword)

        page.listen.start(SEARCH_API_PATTERN)
        page.get(url)

        try:
            packet = page.listen.wait(timeout=15)
        except Exception:
            page.listen.stop()
            return []

        page.listen.stop()

        if not packet or not packet.response:
            return []

        try:
            data = (
                json.loads(packet.response.body)
                if isinstance(packet.response.body, str)
                else packet.response.body
            )
        except (json.JSONDecodeError, AttributeError):
            return []

        return self.extract_tweets(data)

    @staticmethod
    def extract_tweets(data) -> list[dict]:
        """递归遍历 GraphQL SearchTimeline 响应，摘出 tweet 的文本/作者。"""
        tweets = []

        def walk(node):
            if isinstance(node, dict):
                legacy = node.get("legacy")
                if isinstance(legacy, dict) and "full_text" in legacy:
                    user_legacy = (
                        node.get("core", {})
                        .get("user_results", {})
                        .get("result", {})
                        .get("legacy", {})
                    )
                    tweets.append({
                        "text": legacy.get("full_text", ""),
                        "screen_name": user_legacy.get("screen_name", ""),
                        "name": user_legacy.get("name", ""),
                        "created_at": legacy.get("created_at", ""),
                    })
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(data)
        return tweets

    async def close(self):
        if self._page:
            self._page.quit()
            self._page = None
            chrome.persist_profile("x")
