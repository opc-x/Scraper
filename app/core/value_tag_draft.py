"""把用户一句大白话描述转成价值观标签的结构化草稿（正则 + 极性 + 权重）。"""

from __future__ import annotations

PROMPT = """你在帮用户把一句招聘信号描述，转成职位打分系统能用的正则规则。

用户的描述：
{description}

只输出一个 JSON 对象，不要 markdown 代码块、不要任何解释文字：

{{
  "label": "",     // 4-8 个字的标签名，比如「反强制打卡」「弹性工作」
  "pattern": "",   // Python re 正则表达式（字符串形式），要能在职位标题+描述+城市+技能拼接的英文/中文混杂文本里匹配到这个信号，同时覆盖中英文说法，大小写不敏感（调用方会传 re.I）
  "polarity": 1,   // 这个信号命中时对价值观分是加分还是减分：1 = 加分（好信号），-1 = 减分（差信号/红旗）
  "weight": 15,    // 5-30 之间的整数，信号越强越明确权重越高
  "rationale": ""  // 一句话说明为什么这样设计正则和极性，给用户确认时看
}}"""


def render_prompt(description: str) -> str:
    return PROMPT.format(description=description.strip())


def draft_fields(data: dict) -> dict:
    """从模型输出里整理出落库需要的字段，做基本的越界保护。"""
    label = str(data.get("label") or "").strip()[:64] or "未命名标签"
    pattern = str(data.get("pattern") or "").strip()
    polarity = 1 if int(data.get("polarity") or 1) >= 0 else -1
    weight = max(5, min(30, int(data.get("weight") or 15)))
    rationale = str(data.get("rationale") or "").strip()[:500]
    return {"label": label, "pattern": pattern, "polarity": polarity, "weight": weight, "rationale": rationale}
