"""详情页 AI 打标：用户一句判断 + 职位原文 → 已有价值观标签 id。

不新建标签、不写正则。命中的写入 job_value_tags；对不上就空列表。
"""

from __future__ import annotations


PROMPT = """你在帮求职者给这一条职位打已有的价值观标签。

规则：
- 只能从「候选标签」里选 id，禁止发明新标签。
- 用户描述是判断线索，职位原文是证据。两边对得上才选。
- 用户说了但原文完全对不上、或原文有但用户完全没提的，都不要选。
- 一个都对不上就返回空数组。

只输出一个 JSON 对象，不要 markdown：

{{
  "tag_ids": []
}}

--- 候选标签 ---
{catalog}
--- 候选标签结束 ---

--- 职位 ---
{job}
--- 职位结束 ---

--- 用户描述 ---
{note}
--- 用户描述结束 ---
"""


def render_prompt(*, catalog: str, job: str, note: str) -> str:
    return PROMPT.format(catalog=catalog.strip(), job=job.strip(), note=note.strip())


def catalog_text(tags: list) -> str:
    lines = []
    for t in tags:
        desc = str(getattr(t, "description", "") or "").strip()
        extra = f"：{desc}" if desc else ""
        lines.append(f"- id={t.id} 「{t.label}」{extra}")
    return "\n".join(lines) if lines else "（无）"


def parse_tag_ids(data: dict | None, allowed: set[int]) -> list[int]:
    if not isinstance(data, dict):
        return []
    raw = data.get("tag_ids")
    if raw is None:
        raw = data.get("ids")
    if not isinstance(raw, list):
        return []
    seen: set[int] = set()
    out: list[int] = []
    for item in raw:
        try:
            tag_id = int(item)
        except (TypeError, ValueError):
            continue
        if tag_id not in allowed or tag_id in seen:
            continue
        seen.add(tag_id)
        out.append(tag_id)
    return out
