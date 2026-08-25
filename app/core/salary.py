"""薪资文本解析 —— 把各渠道五花八门的薪资串归一成年薪 USD 区间。

抓来的原文长这样：$320K – $320K / $65–$120/hr / 230,000 / year / €80k-100k / 面议
统计和排序都需要一个可比的数字，所以统一折算成年薪美元。
"""

from __future__ import annotations

import re

# 只做粗折算，够用来排序和分桶，不追求汇率精确
FX = {"$": 1.0, "usd": 1.0, "€": 1.08, "eur": 1.08, "£": 1.27, "gbp": 1.27, "¥": 0.14, "cny": 0.14}
PERIOD_MULT = {
    "hour": 2080, "hr": 2080, "h": 2080,
    "day": 260, "d": 260,
    "week": 52, "wk": 52, "w": 52,
    "month": 12, "mo": 12, "m": 12,
    "year": 1, "yr": 1, "annum": 1, "y": 1,
}
VAGUE = {"未披露", "面议", "not specified", "competitive", "doe", "negotiable", "", "无薪"}

NUM = r"(\d[\d,.]*)\s*([kKmM])?"
RANGE_RE = re.compile(
    rf"([$€£¥])?\s*{NUM}\s*(?:[-–—]|to)\s*([$€£¥])?\s*{NUM}"
    rf"(?:\s*(?:per\s+|/\s*)([a-z]+))?", re.I)
SINGLE_RE = re.compile(
    rf"([$€£¥])?\s*{NUM}\s*(?:(usd|eur|gbp|cny)\b)?"
    rf"(?:\s*(?:per\s+|/\s*)([a-z]+))?", re.I)


def _to_num(raw: str, suffix: str | None, inflate_bare: bool) -> float:
    try:
        n = float(raw.replace(",", ""))
    except ValueError:
        return 0.0
    if suffix and suffix.lower() == "k":
        return n * 1_000
    if suffix and suffix.lower() == "m":
        return n * 1_000_000
    # 只有在没写周期时，"120" 这种裸数字才按 120k 理解；
    # 写了 /hr 或 /week 的话 65 就是 65，不能再放大一千倍
    if inflate_bare and 20 < n < 1000:
        return n * 1_000
    return n


def _explicit_period(word: str | None) -> int | None:
    if not word:
        return None
    for key, mult in PERIOD_MULT.items():
        if word.lower().startswith(key):
            return mult
    return None


def _guess_period(amount: float) -> int:
    # 没写周期时按数量级猜：时薪不会有六位数，年薪不会只有两位数
    return 2080 if amount and amount < 400 else 1


def parse(text: str) -> tuple[int, int]:
    """返回 (年薪下限, 年薪上限)，单位 USD；解析不出来返回 (0, 0)。"""
    if not text or text.strip().lower() in VAGUE:
        return 0, 0
    t = text.strip()

    m = RANGE_RE.search(t)
    if m:
        cur1, lo_raw, lo_sfx, cur2, hi_raw, hi_sfx, period = m.groups()
        if not any([cur1, cur2, lo_sfx, hi_sfx, _explicit_period(period)]):
            return 0, 0
        mult = _explicit_period(period)
        bare = mult is None
        lo, hi = _to_num(lo_raw, lo_sfx, bare), _to_num(hi_raw, hi_sfx, bare)
        if mult is None:
            mult = _guess_period(min(x for x in (lo, hi) if x) if (lo or hi) else 0)
        rate = FX.get((cur1 or cur2 or "$").lower(), 1.0)
        lo, hi = int(lo * rate * mult), int(hi * rate * mult)
        return _sane(*((lo, hi) if lo <= hi else (hi, lo)))

    m = SINGLE_RE.search(t)
    if m:
        cur, raw, sfx, code, period = m.groups()
        if not any([cur, code, sfx, _explicit_period(period)]):
            return 0, 0
        mult = _explicit_period(period)
        val = _to_num(raw, sfx, mult is None)
        if not val:
            return 0, 0
        if mult is None:
            mult = _guess_period(val)
        rate = FX.get((cur or code or "$").lower(), 1.0)
        val = int(val * rate * mult)
        return _sane(val, val)
    return 0, 0


# 正则会误吃到岗位编号、电话、融资额一类数字，超出常识区间的一律当没解析出来
SANE_MIN, SANE_MAX = 3_000, 2_000_000


def _sane(lo: int, hi: int) -> tuple[int, int]:
    if hi <= 0 or hi > SANE_MAX or hi < SANE_MIN:
        return 0, 0
    if lo > SANE_MAX or lo < 0:
        return 0, 0
    return lo, hi


def bucket(annual_usd: int) -> str:
    """分桶用于统计图，边界按海外远程岗常见档位划。"""
    if annual_usd <= 0:
        return "未披露"
    for cap, label in ((60_000, "<60K"), (100_000, "60–100K"), (150_000, "100–150K"),
                       (200_000, "150–200K"), (300_000, "200–300K")):
        if annual_usd < cap:
            return label
    return "300K+"


BUCKET_ORDER = ["<60K", "60–100K", "100–150K", "150–200K", "200–300K", "300K+", "未披露"]

# 展示用粗汇率，跟前端 format.ts 保持一致
USD_CNY = 7.14


def format_cny(lo_usd: int = 0, hi_usd: int = 0, *, salary_text: str = "") -> str:
    """给人看的人民币年薪口径。优先从 USD 年薪折算；折算不出再原样返回空。"""
    lo, hi = lo_usd or 0, hi_usd or 0
    if not hi and not lo and salary_text:
        lo, hi = parse(salary_text)
    if not hi and not lo:
        return ""
    def _wan(n: int) -> str:
        wan = n * USD_CNY / 10_000
        if wan >= 10:
            return f"{wan:.0f}万"
        return f"{wan:.1f}万".rstrip("0").rstrip(".")
    if lo and hi and lo != hi:
        return f"约 {_wan(lo)}–{_wan(hi)}/年"
    return f"约 {_wan(hi or lo)}/年"
