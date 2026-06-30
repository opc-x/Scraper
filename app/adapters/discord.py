import json
import logging

import httpx
from app.adapters.base import BaseAdapter
from app.core.channel_config import get_channel_config
from app.core.models import Job, SearchRequest

logger = logging.getLogger(__name__)

DISCORD_API = "https://discord.com/api/v10"

LLM_ENDPOINTS = {
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
}

LLM_MODELS = {
    "deepseek": "deepseek-chat",
}

EXTRACT_PROMPT = """你是一个招聘信息提取助手。从下面的 Discord 频道消息中提取职位信息（消息可能是英文）。

要求：
1. 只提取真实的招聘/求职信息，忽略闲聊、广告、培训
2. 如果消息不包含招聘信息，返回空数组
3. 返回 JSON 格式 {"jobs": [...]}，每个元素：
   - title: 职位名称（保留原文，不强行翻译）
   - company: 公司名（没有则填"未知"）
   - salary: 薪资描述（没有则留空）
   - city: 工作城市（没有则填"远程"）
   - experience: 经验要求
   - education: 学历要求
   - skills: 技能标签数组
   - description: 职位描述/要求摘要（保留关键信息）
   - contact: 联系方式（如有）

只返回 JSON，不要其他内容。"""


DISCORD_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "discord/0.0.309 Chrome/134.0.6998.205 Electron/35.3.0 Safari/537.36"
)


class DiscordAdapter(BaseAdapter):
    name = "discord"

    def __init__(self):
        pass

    @staticmethod
    def _resolve_user_token(cfg: dict) -> str:
        token = (cfg.get("user_token") or "").strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        return token.strip('"').strip("'")

    @staticmethod
    def _auth_headers(user_token: str) -> dict[str, str]:
        return {
            "Authorization": user_token,
            "Content-Type": "application/json",
            "User-Agent": DISCORD_USER_AGENT,
        }

    async def search(self, req: SearchRequest) -> list[Job]:
        cfg = get_channel_config("discord")

        user_token = self._resolve_user_token(cfg)
        if not user_token:
            if (cfg.get("bot_token") or "").strip():
                logger.error("Discord 仍保存着旧 Bot Token，请改填 User Token 后保存")
            else:
                logger.warning("Discord User Token 未配置")
            return []

        sources_raw = cfg.get("sources", "")
        channel_ids = [s.strip() for s in sources_raw.replace(",", "\n").split("\n") if s.strip()]
        if not channel_ids:
            return []

        messages = await self._fetch_from_channels(user_token, channel_ids, req.keyword)
        if not messages:
            return []

        jobs = await self._extract_jobs_with_llm(cfg, messages)

        if req.salary_min:
            jobs = [j for j in jobs if not j.salary or self._salary_above(j.salary, req.salary_min)]
        if req.city:
            jobs = [j for j in jobs if not j.city or req.city in j.city or j.city in ("远程", "Remote", "")]

        return jobs

    async def _fetch_from_channels(
        self, user_token: str, channel_ids: list[str], keyword: str
    ) -> list[str]:
        messages = []
        keyword_lower = keyword.lower() if keyword else ""
        headers = self._auth_headers(user_token)

        async with httpx.AsyncClient(timeout=30) as http:
            resolved_ids = []
            for source_id in channel_ids:
                expanded = await self._expand_if_guild(http, headers, source_id)
                resolved_ids.extend(expanded)

            for channel_id in resolved_ids:
                try:
                    res = await http.get(
                        f"{DISCORD_API}/channels/{channel_id}/messages",
                        headers=headers,
                        params={"limit": 100},
                    )
                    if res.status_code == 401:
                        logger.error("Discord User Token 无效或已过期，请重新从浏览器复制")
                        break
                    if res.status_code == 403:
                        logger.warning("Discord channel %s 无权限访问", channel_id)
                        continue
                    if res.status_code != 200:
                        logger.warning("Discord channel %s fetch failed: %s", channel_id, res.text[:200])
                        continue
                    for msg in res.json():
                        text = msg.get("content", "")
                        if not text or len(text) < 20:
                            continue
                        if keyword_lower and keyword_lower not in text.lower():
                            continue
                        messages.append(text)
                except Exception as e:
                    logger.warning("Failed to fetch from channel %s: %s", channel_id, e)

        return messages

    async def _expand_if_guild(self, http: httpx.AsyncClient, headers: dict, source_id: str) -> list[str]:
        try:
            res = await http.get(f"{DISCORD_API}/guilds/{source_id}/channels", headers=headers)
            if res.status_code != 200:
                return [source_id]
            return [
                ch["id"] for ch in res.json()
                if ch.get("type") == 0  # 文字频道
            ]
        except Exception:
            return [source_id]

    async def _extract_jobs_with_llm(self, cfg: dict, messages: list[str]) -> list[Job]:
        api_key = cfg.get("llm_api_key", "")
        if not api_key:
            return []

        batch_text = "\n\n---\n\n".join(messages[:50])

        endpoint = LLM_ENDPOINTS["deepseek"]
        model = LLM_MODELS["deepseek"]

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": EXTRACT_PROMPT},
                {"role": "user", "content": batch_text},
            ],
            "temperature": 0.1,
        }

        try:
            async with httpx.AsyncClient(timeout=60) as http:
                res = await http.post(endpoint, headers=headers, json=body)
                data = res.json()
                if res.status_code != 200:
                    err = data.get("error", data)
                    logger.error("LLM API failed (%s): %s", res.status_code, err)
                    return []
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return self._parse_llm_response(content)
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            return []

    def _parse_llm_response(self, content: str) -> list[Job]:
        try:
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]
            parsed = json.loads(content)
            items = parsed if isinstance(parsed, list) else parsed.get("jobs", [])
        except (json.JSONDecodeError, AttributeError):
            logger.warning("Failed to parse LLM response: %s", content[:200])
            return []

        jobs = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = item.get("title", "")
            if not title:
                continue
            contact = item.get("contact", "")
            desc = item.get("description", "")
            if contact:
                desc = f"{desc}\n联系方式: {contact}" if desc else f"联系方式: {contact}"
            jobs.append(
                Job(
                    channel="discord",
                    external_id=f"dc_{hash(title + item.get('company', '')) & 0xFFFFFFFF:08x}",
                    title=title,
                    company=item.get("company", "未知"),
                    salary=item.get("salary", ""),
                    city=item.get("city", ""),
                    experience=item.get("experience", ""),
                    education=item.get("education", ""),
                    skills=item.get("skills", []),
                    description=desc,
                    url="",
                    raw=item,
                )
            )
        return jobs

    @staticmethod
    def _salary_above(salary_desc: str, min_val: int) -> bool:
        import re
        m = re.search(r"(\d+)", salary_desc)
        if m:
            num = int(m.group(1))
            if "k" in salary_desc.lower():
                num *= 1000
            return num >= min_val
        return True

    async def close(self):
        pass
