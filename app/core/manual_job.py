"""手工录入职位：粘贴文本 / URL / Markdown 批量，走本机 AI 结构化成
跟自动抓取渠道同一套 ScrapedJob 字段，落库路径复用 persist_scraped_jobs。

展示层会用到的事实字段 + 简历匹配分，都在这一次 AI 调用里算完。
价值观分 / 远程 / 薪资分桶等仍走 persist 时的 apply_derived。
"""

from __future__ import annotations

import re

from app.core import salary as salary_lib
from app.core.resume import PROFILE, resume_text

PROMPT = """你在帮用户把一段招聘信息原文结构化，并对照他的简历给一个匹配分。
原文可能是粘贴文本或网页正文，中英混杂，可能夹杂导航栏/页脚等噪音。

--- 求职者简历（匹配评估用）---
{resume}
--- 简历结束 ---

--- 招聘原文 ---
{content}
--- 原文结束 ---

只输出一个 JSON 对象，不要 markdown 代码块、不要任何解释文字：

{{
  "title": "",
  "company": "",
  "salary": "",
  "salary_cny": "",
  "city": "",
  "is_remote": false,
  "experience": "",
  "education": "",
  "skills": [],
  "district": "",
  "industry": "",
  "stage": "",
  "scale": "",
  "welfare": [],
  "recruiter": "",
  "company_intro": "",
  "sections": [
    {{"title": "岗位信息", "body": "……"}},
    {{"title": "职位要求", "body": "……"}}
  ],
  "description": "",
  "fit_score": 0,
  "verdict": "",
  "one_liner": "",
  "value_tag_ids": []
}}

字段口径：
- title：职位名，看不出填空字符串
- company：公司名，看不出填「未知」
- salary：薪资原文，保留原始写法（美元/人民币/时薪都原样）
- salary_cny：给人看的人民币年薪口径，例如「约 15–20万/年」或「约 100–140万/年」；美元岗按约 7.1 汇率折成年薪人民币；月薪×12；看不出留空
- city：工作城市；纯远程填「远程」
- is_remote：明确可远程 / remote / WFH 则为 true
- experience / education：看不出留空
- skills：技术栈标签数组，最多 20 个
- district / industry / stage / scale / recruiter / company_intro：原文有就抽，没有留空
- welfare：福利数组，没有给 []
- sections：把实质内容拆成 2-6 个有标题的段落（岗位信息、职责、要求、福利、投递方式等），body 用换行和 - 列表，方便详情页排版；不要把导航/页脚塞进去
- description：sections 的纯文本拼接版（给检索/打标签用），保留换行
- fit_score：0-100，对照上面简历的匹配度
- verdict：只能是「强烈推荐」/「值得一投」/「谨慎」/「不建议」之一
- one_liner：一句话说明该不该投
- value_tag_ids：只能从下面的标签库选择；职位原文有明确证据才选，禁止猜测或发明 id

--- 可用自定义标签 ---
{catalog}
--- 标签结束 ---
"""

_VERDICTS = {"强烈推荐", "值得一投", "谨慎", "不建议"}
# Markdown 水平分割线：独占一行的 --- / ---- …
_HR_RE = re.compile(r"(?m)^\s*-{3,}\s*$")
MAX_MARKDOWN_JOBS = 15


def render_prompt(content: str, resume: str | None = None, catalog: str = "（无）") -> str:
    body = (resume if resume is not None else resume_text(4000)) or PROFILE
    return PROMPT.format(content=content.strip()[:8000], resume=body[:4000], catalog=catalog[:6000])


def split_markdown_jobs(text: str) -> list[str]:
    """按 Markdown 水平线 --- 切成多条职位块；空块丢掉。"""
    parts = _HR_RE.split(text or "")
    return [p.strip() for p in parts if p.strip()]


def _str_list(value, *, limit: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    out = [str(item).strip() for item in value if str(item).strip()]
    return out[:limit]


def _sections(data: dict) -> list[dict]:
    raw = data.get("sections")
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw[:8]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()[:64]
        body = str(item.get("body") or "").strip()[:4000]
        if title and body:
            out.append({"title": title, "body": body})
    return out


def job_fields(data: dict) -> dict:
    """从模型输出里整理出 ScrapedJob 列字段。"""
    skills = _str_list(data.get("skills"), limit=20)
    sections = _sections(data)
    description = str(data.get("description") or "").strip()
    if not description and sections:
        description = "\n\n".join(f"## {s['title']}\n{s['body']}" for s in sections)
    city = str(data.get("city") or "").strip()[:64]
    if data.get("is_remote") and not city:
        city = "远程"
    salary = str(data.get("salary") or "").strip()[:64]
    salary_cny = str(data.get("salary_cny") or "").strip()[:64]
    if not salary_cny:
        salary_cny = salary_lib.format_cny(salary_text=salary)[:64]
    return {
        "title": str(data.get("title") or "").strip()[:256],
        "company": str(data.get("company") or "未知").strip()[:256] or "未知",
        "salary": salary,
        "salary_cny": salary_cny,
        "city": city,
        "experience": str(data.get("experience") or "").strip()[:64],
        "education": str(data.get("education") or "").strip()[:64],
        "skills": skills,
        "description": description[:8000],
    }


def extras_for_raw(data: dict) -> dict:
    """详情页从 raw 拆的渠道彩蛋字段 + 分段正文；键名跟 boss 列表字段对齐，方便 _job_extras 复用。"""
    sections = _sections(data)
    recruiter = str(data.get("recruiter") or "").strip()[:128]
    return {
        "areaDistrict": str(data.get("district") or "").strip()[:64],
        "brandIndustry": str(data.get("industry") or "").strip()[:64],
        "brandStageName": str(data.get("stage") or "").strip()[:64],
        "brandScaleName": str(data.get("scale") or "").strip()[:64],
        "welfareList": _str_list(data.get("welfare"), limit=20),
        "bossName": recruiter,
        "brandIntroduce": str(data.get("company_intro") or "").strip()[:2000],
        "sections": sections,
        "is_remote_hint": bool(data.get("is_remote")),
        "fit_score": int(data.get("fit_score") or 0),
        "verdict": str(data.get("verdict") or "").strip()[:32],
        "one_liner": str(data.get("one_liner") or "").strip()[:200],
    }


def match_fields(data: dict) -> dict:
    """录入时一并算出的匹配结论，写入 match_score + job_profiles。"""
    score = int(data.get("fit_score") or 0)
    score = max(0, min(100, score))
    verdict = str(data.get("verdict") or "").strip()
    if verdict not in _VERDICTS:
        if score >= 85:
            verdict = "强烈推荐"
        elif score >= 65:
            verdict = "值得一投"
        elif score >= 40:
            verdict = "谨慎"
        else:
            verdict = "不建议"
    return {
        "fit_score": score,
        "verdict": verdict,
        "one_liner": str(data.get("one_liner") or "").strip()[:200],
        "salary_min_usd": int(data.get("salary_min_usd") or 0),
        "salary_max_usd": int(data.get("salary_max_usd") or 0),
    }


_TAG_STRIP_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+")
_BLANK_RE = re.compile(r"\n{3,}")


def html_to_text(html: str) -> str:
    """从抓下来的网页 HTML 里粗糙抽正文：去 script/style，去标签，压空白。"""
    text = _TAG_STRIP_RE.sub(" ", html)
    text = _TAG_RE.sub("\n", text)
    text = _WS_RE.sub(" ", text)
    text = _BLANK_RE.sub("\n\n", text)
    return text.strip()
