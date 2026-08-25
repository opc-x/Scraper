"""渠道同步查询：解析 `关键字 | 地点 | 天数`，并扩展召回词。"""

from __future__ import annotations

import json
import re

import httpx

from app.infra.llm import LLM_ENDPOINTS, LLM_MODELS

DEFAULT_DAYS = 90
MAX_DAYS = 365

DERIVED = {
    "java": ["jvm", "spring", "spring boot", "kotlin"],
    "nodejs": ["node.js", "typescript", "javascript", "nestjs"],
    "node.js": ["nodejs", "typescript", "javascript", "nestjs"],
    "go": ["golang"],
    "golang": ["go"],
    "ai": ["llm", "machine learning", "agent"],
    "remote": ["远程", "wfh", "work from home"],
    "远程": ["remote", "wfh", "work from home"],
    "杭州": ["hangzhou"],
    "hangzhou": ["杭州"],
}


def _expr(raw: str) -> dict:
    text = raw.strip()
    if not text:
        return {"op": "or", "terms": []}
    operators = re.findall(r"\b(or|and)\b", text, flags=re.I)
    terms = [part.strip() for part in re.split(r"\b(?:or|and)\b", text, flags=re.I) if part.strip()]
    op = "and" if operators and all(item.lower() == "and" for item in operators) else "or"
    return {"op": op, "terms": list(dict.fromkeys(terms))}


def parse_sync_query(raw: str) -> dict:
    normalized = (raw or "").replace("｜", "|").strip()
    columns = [part.strip() for part in normalized.split("|", 2)]
    columns += [""] * (3 - len(columns))
    keyword_expr = _expr(columns[0])
    location_expr = _expr(columns[1])
    try:
        days = int(columns[2]) if columns[2] else DEFAULT_DAYS
    except ValueError:
        days = DEFAULT_DAYS
    days = max(1, min(days, MAX_DAYS))
    return {
        "raw": normalized,
        "keyword_expr": keyword_expr,
        "location_expr": location_expr,
        "within_days": days,
        "derived_keywords": _derive(keyword_expr["terms"]),
        "derived_locations": _derive(location_expr["terms"]),
        "derivation": "dictionary",
    }


def _derive(terms: list[str]) -> list[str]:
    out = list(terms)
    for term in terms:
        out.extend(DERIVED.get(term.lower(), []))
    return list(dict.fromkeys(item for item in out if item))


async def parse_and_derive(raw: str, api_key: str = "") -> dict:
    parsed = parse_sync_query(raw)
    if not api_key or not parsed["keyword_expr"]["terms"]:
        return parsed
    prompt = (
        "为招聘搜索扩展少量同义词和相关技术栈。不得修改用户原词，不得生成时间。"
        "只返回 JSON：{\"keywords\":[],\"locations\":[]}。\n"
        f"关键词：{parsed['keyword_expr']['terms']}\n地点：{parsed['location_expr']['terms']}"
    )
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.post(
                LLM_ENDPOINTS["deepseek"],
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": LLM_MODELS["deepseek"],
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                },
            )
            content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0]
            data = json.loads(content)
            parsed["derived_keywords"] = list(dict.fromkeys([
                *parsed["derived_keywords"],
                *[str(item).strip() for item in data.get("keywords", []) if str(item).strip()],
            ]))
            parsed["derived_locations"] = list(dict.fromkeys([
                *parsed["derived_locations"],
                *[str(item).strip() for item in data.get("locations", []) if str(item).strip()],
            ]))
            parsed["derivation"] = "ai"
    except Exception:  # AI 失败不阻断机械解析和同步
        parsed["derivation"] = "dictionary_fallback"
    return parsed
