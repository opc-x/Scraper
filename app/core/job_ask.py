"""详情页 AI 交互：几个固定动作共用一份 prompt 骨架，只换任务说明。"""

from __future__ import annotations

ACTIONS = {
    "features": "职位特征提取",
    "values": "价值观评分",
    "requirements": "职位要求",
    "preference": "偏好匹配",
    "resume": "简历匹配度",
    "chat": "自由提问",
}

_TASKS = {
    "features": (
        "提取这份职位的硬特征。覆盖：职级/资历、技术栈、业务方向、远程/地点、"
        "协作语言、团队形态、加班/节奏（看不出就写看不出）。不要评价适不适合我。"
    ),
    "values": (
        "给这份职位做价值观评分。默认参照求职者：远程优先、少无效会、技术深度、"
        "能对结果负责、不接受纯外包搬砖。用户如果写了自己的价值观，以用户写的为准。"
        "score 是 0-100 的契合分，bullets 写加分和减分依据，必须引用 JD 原句。"
    ),
    "requirements": (
        "把任职要求拆成：必须具备 / 加分项 / 隐含门槛（年限、学历、签证、时区、英语）。"
        "每条一句话，不要把福利写成要求。"
    ),
    "preference": (
        "先根据用户输入推理出他的真实偏好（3-6 条，写到 inferred），"
        "再逐条对照 JD 判匹配 / 冲突 / 看不出。score 是综合匹配分 0-100。"
        "用户没写具体偏好时，用远程 Java/Agent、少开会、能做技术负责人这些默认偏好。"
    ),
    "resume": (
        "按完整简历评估匹配度。score 即 fit_score 0-100。"
        "必须结合履历独立判断，禁止空话。写清对得上的、缺的、该不该投。"
    ),
    "chat": (
        "回答用户关于这个职位的问题。只根据 JD 和简历，不知道就说不知道。"
    ),
}


def job_context(
    *,
    title: str,
    company: str,
    salary: str,
    city: str,
    skills: list[str],
    channel: str,
    description: str,
) -> str:
    return (
        f"标题：{title or ''}\n"
        f"公司：{company or ''}\n"
        f"薪资：{salary or '未写'}\n"
        f"地点：{city or '未写'}\n"
        f"技术栈：{', '.join(skills) or '未写'}\n"
        f"渠道：{channel}\n"
        f"职位正文：\n{(description or '')[:4000]}"
    )


def render_ask_prompt(*, action: str, context: str, resume: str, message: str) -> str:
    if action not in ACTIONS:
        raise ValueError(f"unknown action: {action}")
    user_note = (message or "").strip() or "（无补充）"
    return f"""你在帮求职者看一份职位。只输出一个 JSON 对象，不要 markdown。

任务：{ACTIONS[action]}
{_TASKS[action]}

--- 简历（默认已有，用户稍后可能替换）---
{resume[:5000]}
--- 简历结束 ---

--- 职位 ---
{context}
--- 职位结束 ---

用户补充：
{user_note}

JSON 字段：
{{
  "title": "{ACTIONS[action]}",
  "summary": "",
  "score": null,
  "bullets": [],
  "inferred": {{}}
}}
score 只在价值观/偏好/简历匹配时填 0-100，其他动作填 null。
inferred 只在偏好匹配时填，key 是推理出的偏好，value 是匹配/冲突/看不出 + 一句依据。
bullets 3-8 条，短句，要有依据。
"""


def normalize_reply(data: dict, action: str) -> dict:
    bullets = data.get("bullets") or []
    if not isinstance(bullets, list):
        bullets = [str(bullets)]
    inferred = data.get("inferred") if isinstance(data.get("inferred"), dict) else {}
    score = data.get("score")
    if score is not None:
        try:
            score = int(score)
        except (TypeError, ValueError):
            score = None
    return {
        "title": str(data.get("title") or ACTIONS.get(action, action)),
        "summary": str(data.get("summary") or ""),
        "score": score,
        "bullets": [str(x).strip() for x in bullets if str(x).strip()],
        "inferred": {str(k): str(v) for k, v in inferred.items()},
        "cached": bool(data.get("cached")),
    }


def profile_to_reply(profile: dict) -> dict:
    match = "、".join(profile.get("stack_match") or []) or "—"
    gap = "、".join(profile.get("stack_gap") or []) or "—"
    bullets = [
        f"结论：{profile.get('verdict') or '—'}",
        f"对得上：{match}",
        f"缺什么：{gap}",
    ]
    if profile.get("salary_note"):
        bullets.append(f"薪资：{profile['salary_note']}")
    if profile.get("china_reason"):
        bullets.append(f"能不能投：{profile.get('china_applicable') or ''} {profile['china_reason']}".strip())
    for tip in (profile.get("apply_tips") or [])[:2]:
        bullets.append(f"建议：{tip}")
    return {
        "title": "简历匹配度",
        "summary": profile.get("one_liner") or "",
        "score": profile.get("fit_score"),
        "bullets": bullets,
        "inferred": {},
        "cached": True,
    }
