"""职位画像 prompt + 落库字段整理——路由（单条，按需生成）和批量脚本共用同一份，
不要各写一套，不然改一次 prompt 两边容易漂移。"""

from __future__ import annotations

from app.core import salary as salary_lib

PROMPT = """你在帮简历所有者评估一个海外远程职位，是否值得投。他的完整简历如下：

--- 简历原文 ---
{resume}
--- 简历原文结束 ---

职位信息：
标题：{title}
公司：{company}
薪资（原文）：{salary}
地点：{city}
技术栈：{skills}
来源渠道：{channel}
原始描述：
{description}

相关评论 / 讨论（可能为空；为空就不要假装有外部口碑）：
{comments}

只输出一个 JSON 对象，不要 markdown 代码块、不要任何解释文字：

{{
  "verdict": "",           // 只能是这四个之一：强烈推荐 / 值得一投 / 谨慎 / 不建议
  "fit_score": 0,          // 0-100，跟他背景的匹配度
  "one_liner": "",         // 一句话结论，直接说该不该投、为什么
  "salary_min_usd": 0,     // 折算成年薪美元的下限，看不出填 0
  "salary_max_usd": 0,
  "salary_note": "",       // 对薪资的判断，比如「低于同类岗位」「按小时计，不稳定」
  "china_applicable": "",  // "可投" / "有条件" / "基本无望"
  "china_reason": "",      // 为什么，具体到时区、工作许可、签证要求
  "stack_match": [],       // 他技能里能对上的
  "stack_gap": [],         // 缺的，需要补的
  "seniority": "",         // 这岗位要的资历
  "hiring_intent": {{
    "type": "",            // 只能是：扩编 / 补缺 / 储备 / 看不出
    "reason": ""           // 依据：必须引用 JD 或评论里的原句，禁止空话。扩编=新业务/加人/growing；补缺=replace/backfill；储备=evergreen/长期招/描述含糊像在收简历
  }},
  "job_portrait": "",      // 这个岗位实际在干什么：日常、汇报线、团队形态、跟谁协作。有评论就用评论交叉验证；没有评论必须写「无外部评论」，只根据 JD 推断并标明不确定处
  "company_profile": "",   // 公司画像：什么阶段、什么业务、团队氛围，看不出就说信息不足
  "red_flags": [],         // 风险点，比如描述含糊、薪资异常低、疑似外包
  "apply_tips": [],        // 投递建议，2-3 条，具体可执行
  "info_quality": ""       // "完整" / "一般" / "信息太少"，原始描述质量
}}"""


def render_prompt(
    *, resume: str, title: str, company: str, salary: str, city: str,
    skills: list[str], channel: str, description: str, comments: str = "",
) -> str:
    return PROMPT.format(
        resume=resume,
        title=title or "", company=company or "", salary=salary or "未写",
        city=city or "未写", skills=", ".join(skills) or "未写", channel=channel,
        description=(description or "")[:3000],
        comments=(comments or "").strip() or "（无）",
    )


def profile_fields(data: dict, fallback_salary: str) -> dict:
    """把模型返回的 JSON 整理成 JobProfile 要落库的字段。"""
    lo = int(data.get("salary_min_usd") or 0)
    hi = int(data.get("salary_max_usd") or 0)
    if not hi:  # 模型没折算出来就用本地解析兜底
        lo, hi = salary_lib.parse(fallback_salary or "")
    return {
        "verdict": str(data.get("verdict") or "")[:32],
        "fit_score": int(data.get("fit_score") or 0),
        "salary_min": lo,
        "salary_max": hi,
    }
