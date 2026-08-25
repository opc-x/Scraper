import hashlib
import json
import logging

import httpx

from app.core.models import Job

logger = logging.getLogger(__name__)

LLM_ENDPOINTS = {
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
}

LLM_MODELS = {
    "deepseek": "deepseek-chat",
}

EXTRACT_PROMPT = """你是一个招聘信息提取助手。从下面的内容中提取职位信息（内容可能是中文或英文）。

要求：
1. 只提取真实的招聘/求职信息，忽略闲聊、广告、培训
2. 如果内容不包含招聘信息，返回空数组
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
   - source_url: 输入中提供的原文链接，必须原样返回

只返回 JSON，不要其他内容。"""


async def extract_jobs(cfg: dict, texts: list[str], channel: str, id_prefix: str) -> list[Job]:
    api_key = cfg.get("llm_api_key", "")
    if not api_key:
        return []

    batch_text = "\n\n---\n\n".join(t for t in texts[:50] if t)
    if not batch_text:
        return []

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": LLM_MODELS["deepseek"],
        "messages": [
            {"role": "system", "content": EXTRACT_PROMPT},
            {"role": "user", "content": batch_text},
        ],
        "temperature": 0.1,
    }

    try:
        async with httpx.AsyncClient(timeout=60) as http:
            res = await http.post(LLM_ENDPOINTS["deepseek"], headers=headers, json=body)
            data = res.json()
            if res.status_code != 200:
                logger.error("LLM API failed (%s): %s", res.status_code, data.get("error", data))
                return []
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return parse_jobs(content, channel=channel, id_prefix=id_prefix)
    except Exception as e:
        logger.error("LLM call failed: %s", e)
        return []


def parse_jobs(content: str, channel: str, id_prefix: str) -> list[Job]:
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
        source_url = str(item.get("source_url") or item.get("url") or "")
        dedup_key = f"{title}|{item.get('company', '')}|{source_url}".encode()
        jobs.append(
            Job(
                channel=channel,
                external_id=f"{id_prefix}_{hashlib.md5(dedup_key).hexdigest()[:16]}",
                title=title,
                company=item.get("company", "未知"),
                salary=item.get("salary", ""),
                city=item.get("city", ""),
                experience=item.get("experience", ""),
                education=item.get("education", ""),
                skills=item.get("skills", []),
                description=desc,
                url=str(item.get("source_url") or item.get("url") or "")[:512],
                raw=item,
            )
        )
    return jobs
