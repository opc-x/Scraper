"""从渠道约定 / raw / 正文把缺失的原文链接和 Discord 地点补回来。

各渠道写入时字段名不统一，列表页的「原文」只认 scraped_jobs.url。
能从 external_id 或 raw 唯一还原的就还原；还原不了就留空，不要编链接。
"""

from __future__ import annotations

import re

_HTTP_RE = re.compile(r"^https?://", re.I)
_APPLY_URL_RE = re.compile(
    r"https?://[^\s)<>\"']*"
    r"(?:greenhouse\.io|lever\.co|ashbyhq\.com|myworkdayjobs\.com|"
    r"smartrecruiters\.com|workable\.com|otta\.com|"
    r"(?:jobs|careers)\.)"
    r"[^\s)<>\"']*",
    re.I,
)
_GENERIC_CITY_RE = re.compile(
    r"^(hybrid|remote|on-?site|not specified|unspecified|n/?a|未知)$", re.I
)
_LEVEL_RE = re.compile(
    r"^(senior|junior|jr\.?|mid(?:-level)?|staff|principal|lead|intern|entry)\b", re.I
)
_SKILL_LEAK_RE = re.compile(
    r"\s+(?:Java|Python|TypeScript|JavaScript|React|Node\.?js|Go|Rust|"
    r"Kotlin|AWS|GCP|Azure|Kubernetes|Docker|GraphQL|SQL)\b",
    re.I,
)
_FIRE_LOC_RE = re.compile(
    r"\$[\d,.]+K?(?:\s*[–—-]\s*\$?[\d,.]+K?)?\s*[·•]\s*([^·•\n]{2,80}?)\s*[·•]",
    re.I,
)
_LOCATION_LINE_RE = re.compile(r"(?:^|\n)\s*Location\s*[:：]\s*([^\n]{2,80})", re.I)
_REMOTE_PLACE_RE = re.compile(
    r"\b(Remote|Hybrid|On-site)\s*[•·,-]\s*([^\n|]{2,80})", re.I
)
_DISCORD_CHANNEL_RE = re.compile(r"discord\.com/channels/(\d+)", re.I)
_SOURCE_RAW_KEYS = ("source_server", "source_channel", "source_account")
DISCORD_GUILD_NAMES = {
    "174075418410876928": "devcord",
    "231471142685245440": "Rythm",
    "554623348622098432": "ETHGlobal",
    "698366411864670250": "cscareers.dev",
    "851527874828566558": "Invide",
    "880546729349488741": "Devs For Hire",
    "944133153105276979": "For Hire",
    "969872191179071498": "Cookie",
    "1002522561613135892": "Freelance Marketplace",
    "1074847526655643750": "Cursor",
    "1116994814349688875": "Job cord",
    "1172568727942860810": "Google Labs",
    "1224897044259278858": "NextJob",
    "1297484076407853147": "FreeLanceBase",
    "1456350064065904867": "OpenClaw",
    "1488674851345531057": "CronJobs",
}


def source_label(channel: str = "", raw: dict | None = None, url: str = "") -> str:
    """卡片上来源标注：Discord 用 server 名，Telegram 用频道，X 用账号。"""
    blob = raw if isinstance(raw, dict) else {}
    for key in _SOURCE_RAW_KEYS:
        val = str(blob.get(key) or "").strip()
        if val and val.lower() not in {"unknown", "未知", "n/a"}:
            return val[:64]
    if (channel or "").strip().lower() == "discord":
        gid = str(blob.get("guild_id") or "").strip()
        if not gid:
            match = _DISCORD_CHANNEL_RE.search(url or "")
            gid = match.group(1) if match else ""
        if gid:
            return DISCORD_GUILD_NAMES.get(gid, gid)[:64]
    return ""


def _http(value: str) -> str:
    text = (value or "").strip()
    if not _HTTP_RE.match(text):
        return ""
    return text.rstrip(".,;\"'")[:512]


def origin_url(
    channel: str,
    external_id: str = "",
    url: str = "",
    raw: dict | None = None,
    description: str = "",
) -> str:
    """已有合法 http(s) 链接就原样用；否则按渠道从 id/raw/正文还原。"""
    found = _http(url)
    if found:
        return found
    blob = raw if isinstance(raw, dict) else {}
    for key in ("source_url", "url", "link", "apply_url"):
        found = _http(str(blob.get(key) or ""))
        if found:
            return found

    ch = (channel or "").strip().lower()
    ext = (external_id or "").strip()

    if ch == "boss" and ext:
        return f"https://www.zhipin.com/job_detail/{ext}.html"[:512]
    if ch == "v2ex":
        tid = str(blob.get("topic_id") or "").strip() or ext.removeprefix("v2ex_")
        tid = tid.split("#", 1)[0]
        if tid:
            return f"https://www.v2ex.com/t/{tid}"[:512]
    if ch == "hackernews":
        pid = str(blob.get("post_id") or "").strip() or ext.removeprefix("hn_")
        if pid:
            return f"https://news.ycombinator.com/item?id={pid}"[:512]
    if ch == "telegram":
        post = str(blob.get("post") or "").strip()
        if post:
            return f"https://t.me/{post}"[:512]
    if ch in {"x", "x_zh"}:
        handle = str(blob.get("source_account") or "").strip().lstrip("@")
        if handle:
            return f"https://x.com/{handle}"[:512]
    if ch == "eleduck" and ext:
        return f"https://eleduck.com/posts/{ext}"[:512]
    if ch == "discord":
        match = _APPLY_URL_RE.search(description or "")
        if match:
            return _http(match.group(0))
    return ""


def _clean_city(raw: str) -> str:
    loc = re.sub(r"\s+", " ", raw or "").strip(" ·•|-")
    loc = _SKILL_LEAK_RE.split(loc, maxsplit=1)[0].strip(" ·•|-")
    if not loc or _GENERIC_CITY_RE.match(loc):
        return ""
    return loc[:64]


def city_from_discord_text(text: str) -> str:
    """CronJobs JobsBot 把地点写在薪资行中间：`$146K – $200K · San Francisco, CA · Mid-level`。"""
    blob = text or ""
    match = _FIRE_LOC_RE.search(blob)
    if match:
        loc = _clean_city(match.group(1))
        if loc:
            return loc
    match = _LOCATION_LINE_RE.search(blob)
    if match:
        loc = _clean_city(match.group(1))
        if loc:
            return loc
    match = _REMOTE_PLACE_RE.search(blob)
    if match:
        place = _clean_city(match.group(2))
        if place and not _LEVEL_RE.match(place) and not _GENERIC_CITY_RE.match(place):
            return place
    if re.search(r"\bremote\b|远程", blob, re.I):
        return "远程"
    return ""


def telegram_message_url(
    username: str = "", entity_id: int | None = None, msg_id: int | None = None,
) -> str:
    """公开频道走 t.me/<user>/<id>；私有频道走 t.me/c/<internal>/<id>。"""
    if not msg_id:
        return ""
    name = (username or "").strip().lstrip("@")
    if name:
        return f"https://t.me/{name}/{msg_id}"[:512]
    if entity_id is None:
        return ""
    internal = str(entity_id)
    if internal.startswith("-100"):
        internal = internal[4:]
    elif internal.startswith("-"):
        internal = internal[1:]
    if not internal:
        return ""
    return f"https://t.me/c/{internal}/{msg_id}"[:512]
