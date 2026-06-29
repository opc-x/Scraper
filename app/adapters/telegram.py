import json
import logging

import httpx
from app.adapters.base import BaseAdapter
from app.core.channel_config import get_channel_config
from app.core.models import Job, SearchRequest
from app.core.telegram_client import get_telegram_client

logger = logging.getLogger(__name__)

LLM_ENDPOINTS = {
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
}

LLM_MODELS = {
    "deepseek": "deepseek-chat",
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-6-20250514",
}

EXTRACT_PROMPT = """你是一个招聘信息提取助手。从下面的聊天消息中提取职位信息。

要求：
1. 只提取真实的招聘/求职信息，忽略闲聊、广告、培训
2. 如果消息不包含招聘信息，返回空数组
3. 返回 JSON 格式 {"jobs": [...]}，每个元素：
   - title: 职位名称
   - company: 公司名（没有则填"未知"）
   - salary: 薪资描述（没有则留空）
   - city: 工作城市（没有则填"远程"）
   - experience: 经验要求
   - education: 学历要求
   - skills: 技能标签数组
   - description: 职位描述/要求摘要（保留关键信息）
   - contact: 联系方式（如有）

只返回 JSON，不要其他内容。"""


class TelegramAdapter(BaseAdapter):
    name = "telegram"

    def __init__(self):
        pass

    async def search(self, req: SearchRequest) -> list[Job]:
        cfg = get_channel_config("telegram")

        client = await get_telegram_client()
        if not client:
            return []

        messages = []

        group_ids_raw = cfg.get("group_ids", "")
        groups = [g.strip() for g in group_ids_raw.replace(",", "\n").split("\n") if g.strip()]
        if groups:
            msgs = await self._fetch_from_entities(client, groups, req.keyword)
            messages.extend(msgs)

        dm_ids_raw = cfg.get("dm_users", "")
        dm_users = [u.strip() for u in dm_ids_raw.replace(",", "\n").split("\n") if u.strip()]
        if dm_users:
            msgs = await self._fetch_from_entities(client, dm_users, req.keyword)
            messages.extend(msgs)

        if not messages:
            return []

        jobs = await self._extract_jobs_with_llm(cfg, messages)

        if req.salary_min:
            jobs = [j for j in jobs if not j.salary or self._salary_above(j.salary, req.salary_min)]
        if req.city:
            jobs = [j for j in jobs if not j.city or req.city in j.city or j.city in ("远程", "Remote", "")]

        return jobs

    async def _fetch_from_entities(
        self, client, refs: list[str], keyword: str
    ) -> list[str]:
        messages = []
        keyword_lower = keyword.lower() if keyword else ""

        for ref in refs:
            try:
                try:
                    entity = int(ref) if ref.lstrip("-").isdigit() else ref
                except ValueError:
                    entity = ref

                entity = await client.get_entity(entity)

                async for msg in client.iter_messages(entity, limit=100):
                    if not msg.text or len(msg.text) < 20:
                        continue
                    if keyword_lower and keyword_lower not in msg.text.lower():
                        continue
                    messages.append(msg.text)

            except Exception as e:
                logger.warning("Failed to fetch from %s: %s", ref, e)

        return messages

    async def _extract_jobs_with_llm(self, cfg: dict, messages: list[str]) -> list[Job]:
        provider = cfg.get("llm_provider", "deepseek")
        api_key = cfg.get("llm_api_key", "")
        base_url = cfg.get("llm_base_url", "")

        if not api_key:
            return []

        batch_text = "\n\n---\n\n".join(messages[:50])

        if provider == "anthropic":
            return await self._call_anthropic(api_key, base_url, batch_text)

        endpoint = base_url.rstrip("/") + "/chat/completions" if base_url else LLM_ENDPOINTS.get(provider, LLM_ENDPOINTS["deepseek"])
        model = LLM_MODELS.get(provider, "deepseek-chat")

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
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return self._parse_llm_response(content)
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            return []

    async def _call_anthropic(self, api_key: str, base_url: str, text: str) -> list[Job]:
        url = (base_url.rstrip("/") or "https://api.anthropic.com") + "/v1/messages"
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body = {
            "model": LLM_MODELS["anthropic"],
            "max_tokens": 4096,
            "system": EXTRACT_PROMPT,
            "messages": [{"role": "user", "content": text}],
        }
        try:
            async with httpx.AsyncClient(timeout=60) as http:
                res = await http.post(url, headers=headers, json=body)
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
                    channel="telegram",
                    external_id=f"tg_{hash(title + item.get('company', '')) & 0xFFFFFFFF:08x}",
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
