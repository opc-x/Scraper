"""用户一句话需求 → SOP 方案。本机模型出草稿，解析失败就按需求拆步。"""

from __future__ import annotations

import re

from app.core.default_sop import DEFAULT_SOP_STEPS

MODELS = ("claude", "codex", "cursor")

PROMPT = """你在给一份简历出审稿 SOP。只出洞、不改稿。

用户需求：
{brief}

可用模型：{models}
每一步 from 必须是其中一个。只选了一个就把每一步都派给它。选了多个就按谁适合干什么分，不要平均凑数。

步数按需求来，3 到 8 步，不要固定五步。

只输出一个 JSON 对象，不要 markdown 代码块：

{{
  "title": "不超过 12 字的方案名",
  "description": "一两句说这套 SOP 干什么",
  "steps": [
    {{"title": "短名", "body": "这一步具体干什么", "from": "claude"}}
  ]
}}
"""


def normalize_models(raw: list[str] | None) -> list[str]:
    seen: list[str] = []
    for item in raw or []:
        name = str(item or "").strip().lower()
        if name in MODELS and name not in seen:
            seen.append(name)
    return seen or ["claude"]


def render_prompt(brief: str, models: list[str]) -> str:
    return PROMPT.format(brief=brief.strip(), models="、".join(models))


def _step_id(i: int) -> str:
    return f"s{i}"


def _assign(i: int, models: list[str]) -> str:
    return models[i % len(models)]


def fallback_plan(brief: str, models: list[str]) -> dict:
    lines = [
        re.sub(r"^[\-\*\d\.、\s]+", "", line).strip()
        for line in brief.splitlines()
        if line.strip()
    ]
    lines = [x for x in lines if x]
    if len(lines) >= 2:
        steps = [
            {
                "id": _step_id(i),
                "from": _assign(i - 1, models),
                "at": "",
                "title": line[:16],
                "body": line[:200],
            }
            for i, line in enumerate(lines[:8], start=1)
        ]
    else:
        steps = []
        for i, raw in enumerate(DEFAULT_SOP_STEPS, start=1):
            step = dict(raw)
            step["id"] = _step_id(i)
            step["from"] = _assign(i - 1, models)
            step["at"] = ""
            steps.append(step)
    desc = (lines[0] if lines else brief).strip()[:200] or "按你写的需求审这份简历。"
    return {"title": sop_title(brief, desc, steps), "description": desc, "steps": steps}


def sop_title(brief: str, description: str, steps: list[dict]) -> str:
    raw = str(description or "").split("。")[0].split("，")[0].strip()
    raw = re.sub(r"^这套\s*SOP\s*", "", raw).strip()
    if not raw or raw.startswith("只审") and steps:
        raw = str(steps[0].get("title") or "").strip() or raw
    if not raw:
        raw = str(brief or "").split("。")[0].split("，")[0].strip()
    if not raw and steps:
        raw = str(steps[0].get("title") or "").strip()
    return (raw or "SOP")[:12]


def parse_plan(data: dict | None, *, brief: str, models: list[str]) -> dict:
    if not isinstance(data, dict):
        return fallback_plan(brief, models)
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        return fallback_plan(brief, models)
    steps: list[dict] = []
    for i, raw in enumerate(raw_steps[:8], start=1):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()[:24]
        body = str(raw.get("body") or "").strip()[:400]
        if not title:
            continue
        who = str(raw.get("from") or "").strip().lower()
        if who not in models:
            who = _assign(i - 1, models)
        steps.append({"id": _step_id(i), "from": who, "at": "", "title": title, "body": body})
    if not steps:
        return fallback_plan(brief, models)
    desc = str(data.get("description") or "").strip()[:200] or fallback_plan(brief, models)["description"]
    title = str(data.get("title") or "").strip()[:16] or sop_title(brief, desc, steps)
    return {"title": title, "description": desc, "steps": steps}
