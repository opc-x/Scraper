import asyncio
import json
import logging

from app.adapters.base import BaseAdapter
from app.core.channel_config import get_channel_config
from app.core.models import Job, SearchRequest
from app.infra import chrome, llm

logger = logging.getLogger(__name__)

SEARCH_API_PATTERN = "SearchTimeline"
USER_TWEETS_API_PATTERN = "UserTweets"
X_SEARCH_URL = "https://x.com/search?q={query}&src=typed_query&f=live"
X_PROFILE_URL = "https://x.com/{screen_name}"


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

    def fetch_user_tweets_sync(self, screen_name: str, timeout: int = 15) -> list[dict]:
        """访问某账号主页，抓一屏最近发帖（用于账号历史评估，不是搜索）。"""
        page = self._ensure_page()
        url = X_PROFILE_URL.format(screen_name=screen_name)

        page.listen.start(USER_TWEETS_API_PATTERN)
        page.get(url)

        try:
            packet = page.listen.wait(timeout=timeout)
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

    def fetch_user_profile_sync(self, screen_name: str, timeout: int = 15) -> dict | None:
        """访问账号主页，从 UserTweets 响应里摘出该账号的完整 profile（粉丝数/简介/头像等），用于建账号档案表。"""
        page = self._ensure_page()
        url = X_PROFILE_URL.format(screen_name=screen_name)

        page.listen.start(USER_TWEETS_API_PATTERN)
        page.get(url)

        try:
            packet = page.listen.wait(timeout=timeout)
        except Exception:
            page.listen.stop()
            return None

        page.listen.stop()

        if not packet or not packet.response:
            return None

        try:
            data = (
                json.loads(packet.response.body)
                if isinstance(packet.response.body, str)
                else packet.response.body
            )
        except (json.JSONDecodeError, AttributeError):
            return None

        return self.extract_user_profile(data)

    @staticmethod
    def extract_user_profile(data) -> dict | None:
        """递归找到响应里第一个完整的 User 对象（user_results.result），返回原始 dict。"""
        def walk(node):
            if isinstance(node, dict):
                user_results = node.get("user_results")
                if isinstance(user_results, dict):
                    result = user_results.get("result")
                    if isinstance(result, dict) and result.get("__typename") == "User":
                        return result
                for v in node.values():
                    found = walk(v)
                    if found is not None:
                        return found
            elif isinstance(node, list):
                for item in node:
                    found = walk(item)
                    if found is not None:
                        return found
            return None

        return walk(data)

    @staticmethod
    def extract_tweets(data) -> list[dict]:
        """递归遍历 GraphQL SearchTimeline 响应，摘出 tweet 的文本/作者。"""
        tweets = []

        def walk(node):
            if isinstance(node, dict):
                legacy = node.get("legacy")
                if isinstance(legacy, dict) and "full_text" in legacy:
                    user_result = (
                        node.get("core", {})
                        .get("user_results", {})
                        .get("result", {})
                    )
                    # 用户名/昵称在 result.core 里，legacy 是旧字段位置，两个都兜一下
                    user_core = user_result.get("core", {})
                    user_legacy = user_result.get("legacy", {})
                    # bio 也从 legacy.description 挪到了 profile_bio.description（2026-08 抓包实测确认，跟 screen_name 同一次迁移）
                    bio = user_result.get("profile_bio", {}).get("description") or user_legacy.get("description", "")
                    tweets.append({
                        "text": legacy.get("full_text", ""),
                        "screen_name": user_core.get("screen_name") or user_legacy.get("screen_name", ""),
                        "name": user_core.get("name") or user_legacy.get("name", ""),
                        "created_at": legacy.get("created_at", ""),
                        "bio": bio,
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
