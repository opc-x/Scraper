import asyncio
import json
import logging

import httpx

from app.adapters.base import BaseAdapter
from app.core.channel_config import get_channel_config
from app.core.models import Job, SearchRequest

logger = logging.getLogger(__name__)

LLM_ENDPOINTS = {
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
}

LLM_MODELS = {
    "deepseek": "deepseek-chat",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-6-20250514",
}

EXTRACT_PROMPT = """你是一个招聘信息提取助手。从下面的聊天消息中提取职位信息。

要求：
1. 只提取真实的招聘/求职信息，忽略闲聊
2. 如果消息不包含招聘信息，返回空数组
3. 返回 JSON 数组，每个元素包含以下字段：
   - title: 职位名称
   - company: 公司名（没有则填"未知"）
   - salary: 薪资描述（没有则填空）
   - city: 工作城市（没有则填"远程"）
   - experience: 经验要求
   - education: 学历要求
   - skills: 技能标签数组
   - description: 职位描述摘要
   - is_job: true 表示招聘信息，false 表示不是

只返回 JSON，不要其他内容。"""


class TelegramAdapter(BaseAdapter):
    name = "telegram"

    def __init__(self):
        self._polling_task: asyncio.Task | None = None

    async def search(self, req: SearchRequest) -> list[Job]:
        cfg = get_channel_config("telegram")
        bot_token = cfg.get("bot_token", "")
        group_ids_raw = cfg.get("group_ids", "")

        if not bot_token or not group_ids_raw:
            return []

        group_ids = [g.strip() for g in group_ids_raw.replace(",", "\n").split("\n") if g.strip()]
        if not group_ids:
            return []

        messages = await self._fetch_recent_messages(bot_token, group_ids)
        if not messages:
            return []

        keyword = req.keyword.lower() if req.keyword else ""
        relevant = [m for m in messages if keyword in m.lower()] if keyword else messages

        if not relevant:
            return []

        jobs = await self._extract_jobs_with_llm(cfg, relevant)

        if req.salary_min:
            jobs = [j for j in jobs if not j.salary or self._salary_above(j.salary, req.salary_min)]
        if req.city:
            jobs = [j for j in jobs if not j.city or req.city in j.city or j.city in ("远程", "Remote", "")]

        return jobs

    async def _fetch_recent_messages(self, bot_token: str, group_ids: list[str]) -> list[str]:
        messages = []
        async with httpx.AsyncClient(timeout=15) as client:
            for gid in group_ids:
                try:
                    url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
                    res = await client.get(url, params={"offset": -100, "allowed_updates": '["message"]'})
                    data = res.json()
                    if not data.get("ok"):
                        logger.warning("Telegram API error for group %s: %s", gid, data)
                        continue
                    for update in data.get("result", []):
                        msg = update.get("message", {})
                        chat_id = str(msg.get("chat", {}).get("id", ""))
                        text = msg.get("text", "")
                        if chat_id == gid and text and len(text) > 20:
                            messages.append(text)
                except Exception as e:
                    logger.warning("Failed to fetch from group %s: %s", gid, e)
        return messages

    async def _extract_jobs_with_llm(self, cfg: dict, messages: list[str]) -> list[Job]:
        provider = cfg.get("llm_provider", "deepseek")
        api_key = cfg.get("llm_api_key", "")
        base_url = cfg.get("llm_base_url", "")

        if not api_key:
            return []

        endpoint = base_url.rstrip("/") + "/chat/completions" if base_url else LLM_ENDPOINTS.get(provider, "")
        model = LLM_MODELS.get(provider, "deepseek-chat")

        batch_text = "\n---\n".join(messages[:50])

        if provider == "anthropic":
            return await self._call_anthropic(cfg, batch_text)

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": EXTRACT_PROMPT},
                {"role": "user", "content": batch_text},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                res = await client.post(endpoint, headers=headers, json=body)
                data = res.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return self._parse_llm_response(content)
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            return []

    async def _call_anthropic(self, cfg: dict, text: str) -> list[Job]:
        api_key = cfg.get("llm_api_key", "")
        base_url = cfg.get("llm_base_url", "").rstrip("/") or "https://api.anthropic.com"
        model = LLM_MODELS["anthropic"]

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "max_tokens": 4096,
            "system": EXTRACT_PROMPT,
            "messages": [{"role": "user", "content": text}],
        }

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                res = await client.post(f"{base_url}/v1/messages", headers=headers, json=body)
                data = res.json()
                content = data.get("content", [{}])[0].get("text", "")
                return self._parse_llm_response(content)
        except Exception as e:
            logger.error("Anthropic call failed: %s", e)
            return []

    def _parse_llm_response(self, content: str) -> list[Job]:
        try:
            content = content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]
            parsed = json.loads(content)
            items = parsed if isinstance(parsed, list) else parsed.get("jobs", parsed.get("data", []))
        except (json.JSONDecodeError, AttributeError):
            logger.warning("Failed to parse LLM response")
            return []

        jobs = []
        for item in items:
            if not isinstance(item, dict) or not item.get("is_job", True):
                continue
            title = item.get("title", "")
            if not title:
                continue
            jobs.append(
                Job(
                    channel="telegram",
                    external_id=f"tg_{hash(title + item.get('company', '')) & 0xFFFFFFFF:08x}",
                    title=title,
                    company=item.get("company", "未知"),
                    salary=item.get("salary", ""),
                    city=item.get("city", ""),
                    experience=item.get("experience", ""),
                    education=item.get("education", ""),
                    skills=item.get("skills", []),
                    description=item.get("description", ""),
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
            if "k" in salary_desc.lower() or "K" in salary_desc:
                num *= 1000
            return num >= min_val
        return True

    async def close(self):
        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()
            self._polling_task = None
