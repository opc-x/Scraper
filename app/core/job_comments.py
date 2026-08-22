"""生成单条画像时现查公开评论：HN 讨论 + Reddit 归档。失败就当没有，不挡画像。

不跑 Glassdoor 登录墙；HN/Reddit 上本来就有人贴 Glassdoor 摘要，搜那些。
只在点「生成画像」/批量 profile_jobs 时按这一条公司去查，不给全库预刷。
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)
_lock = threading.Lock()
_hn_cache: dict[str, list[str]] = {}
_rd_cache: dict[str, list[str]] = {}

UA = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json,text/html;q=0.9",
}

_COOKIE_FILE = os.path.join(
    os.path.expanduser("~/.scraper/chrome_profiles"), "reddit", "request_cookies.txt"
)
_SKIP = {
    "", "未知", "unknown", "n/a", "na", "remote", "hiring", "confidential",
    "stealth", "匿名", "redacted", "company", "various",
}
_NOISE = re.compile(
    r"\b(inc|llc|ltd|gmbh|corp|corporation|limited|co|the|有限公司|集团)\b", re.I
)
_HTML = re.compile(r"<[^>]+>")
_STORED_KEYS = (
    "comments", "replies", "discussion", "thread_replies",
    "hn_children", "kids_text", "reviews",
)


def company_query(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"https?://", "", s)
    s = s.split("/")[0]
    s = re.sub(r"\.(com|io|ai|co|dev|net|org|app)$", "", s, flags=re.I)
    s = _NOISE.sub(" ", s)
    s = re.sub(r"[\"'()]", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .,|-")
    if s.lower() in _SKIP or len(s) < 3:
        return ""
    return s


def import_reddit_cookies_from_chrome() -> bool:
    """从本机日常 Chrome（最近使用的 profile）抠 Reddit Cookie。"""
    try:
        import browser_cookie3  # type: ignore
    except ImportError:
        return False
    base = os.path.expanduser("~/Library/Application Support/Google/Chrome")
    profile = "Default"
    try:
        import json as _json
        st = _json.load(open(os.path.join(base, "Local State"), encoding="utf-8"))
        profile = (st.get("profile") or {}).get("last_used") or "Default"
    except Exception:
        pass
    cookie_db = os.path.join(base, profile, "Cookies")
    if not os.path.isfile(cookie_db):
        return False
    try:
        jar = browser_cookie3.chrome(cookie_file=cookie_db, domain_name="reddit.com")
    except Exception as e:  # noqa: BLE001
        logger.info("读 Chrome Cookie 失败：%s", e)
        return False
    header = "; ".join(f"{c.name}={c.value}" for c in jar if c.value)
    if "reddit_session=" not in header:
        return False
    os.makedirs(os.path.dirname(_COOKIE_FILE), exist_ok=True)
    with open(_COOKIE_FILE, "w", encoding="ascii", errors="ignore") as f:
        f.write(header)
    return True


def _headers_for(url: str) -> dict[str, str]:
    headers = dict(UA)
    if "reddit.com" not in url:
        return headers
    if not os.path.isfile(_COOKIE_FILE):
        import_reddit_cookies_from_chrome()
    if os.path.isfile(_COOKIE_FILE):
        cookie = open(_COOKIE_FILE, encoding="utf-8").read().strip()
        cookie = cookie.encode("latin-1", "ignore").decode("latin-1")
        if cookie:
            headers["Cookie"] = cookie
    return headers


def _get_json(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers=_headers_for(url))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _clean(text: str) -> str:
    text = _HTML.sub(" ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _stored(raw: dict | None) -> list[str]:
    if not isinstance(raw, dict):
        return []
    chunks: list[str] = []
    for key in _STORED_KEYS:
        val = raw.get(key)
        if not val:
            continue
        if isinstance(val, str):
            chunks.append(_clean(val))
        elif isinstance(val, list):
            for item in val[:15]:
                if isinstance(item, str):
                    chunks.append(_clean(item))
                elif isinstance(item, dict):
                    text = item.get("text") or item.get("body") or item.get("comment") or ""
                    if text:
                        author = item.get("author") or item.get("by") or ""
                        chunks.append(_clean(f"{author}: {text}" if author else text))
    return [c for c in chunks if len(c) > 20]


def _hn_item_replies(external_id: str) -> list[str]:
    if not external_id.isdigit():
        return []
    data = _get_json(f"https://hn.algolia.com/api/v1/items/{external_id}")
    out: list[str] = []

    def walk(node: dict, depth: int = 0) -> None:
        if depth > 2 or len(out) >= 8:
            return
        text = _clean(node.get("text") or "")
        if text and depth > 0:
            by = node.get("author") or ""
            out.append(f"HN @{by}: {text[:400]}")
        for child in node.get("children") or []:
            if isinstance(child, dict):
                walk(child, depth + 1)

    walk(data)
    return out


def _hn_search(company: str) -> list[str]:
    with _lock:
        if company in _hn_cache:
            return _hn_cache[company]
    q = urllib.parse.quote(f'"{company}" (hiring OR interview OR glassdoor OR layoff OR remote)')
    url = f"https://hn.algolia.com/api/v1/search?query={q}&tags=comment&hitsPerPage=8"
    hits = _get_json(url).get("hits") or []
    out: list[str] = []
    for h in hits:
        text = _clean(h.get("comment_text") or h.get("story_text") or "")
        if len(text) < 40:
            continue
        if company.lower() not in text.lower() and company.lower() not in (h.get("story_title") or "").lower():
            continue
        title = h.get("story_title") or ""
        out.append(f"HN / {title}: {text[:400]}")
        if len(out) >= 6:
            break
    with _lock:
        _hn_cache[company] = out
    return out


def _reddit_hits(payload: dict) -> list[dict]:
    data = payload.get("data")
    if isinstance(data, dict):
        return [c.get("data") or {} for c in data.get("children") or []]
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _reddit_search(company: str) -> list[str]:
    with _lock:
        if company in _rd_cache:
            return _rd_cache[company]
    q = urllib.parse.quote(f"{company} work OR interview OR glassdoor OR hiring")
    urls = [
        f"https://www.reddit.com/search.json?q={q}&sort=relevance&t=year&limit=10&type=comment",
        f"https://api.pullpush.io/reddit/search/comment/?q={q}&size=10",
    ]
    out: list[str] = []
    for url in urls:
        try:
            rows = _reddit_hits(_get_json(url))
        except Exception as e:  # noqa: BLE001
            logger.info("Reddit 源失败 %s：%s", url.split("/")[2], e)
            continue
        for row in rows:
            text = _clean(row.get("body") or row.get("selftext") or row.get("title") or "")
            if len(text) < 40:
                continue
            if company.lower() not in text.lower():
                continue
            sub = row.get("subreddit") or ""
            out.append(f"Reddit r/{sub}: {text[:400]}")
            if len(out) >= 6:
                with _lock:
                    _rd_cache[company] = out
                return out
    with _lock:
        _rd_cache[company] = out
    return out


def gather_comments(
    *,
    company: str,
    channel: str = "",
    external_id: str = "",
    raw: dict | None = None,
    limit: int = 2200,
) -> tuple[str, list[str]]:
    """返回 (评论文本, 来源标签)。任一源失败就跳过。"""
    parts: list[str] = []
    sources: list[str] = []

    stored = _stored(raw)
    if stored:
        parts.extend(stored[:8])
        sources.append("帖内讨论")

    q = company_query(company)
    if not q:
        text = "\n---\n".join(parts)
        return text[:limit], sources

    try:
        if channel == "hackernews":
            replies = _hn_item_replies(str(external_id or ""))
            if replies:
                parts.extend(replies)
                sources.append("HN帖下回复")
    except Exception as e:  # noqa: BLE001
        logger.info("HN item 评论拉取失败：%s", e)

    try:
        hn = _hn_search(q)
        if hn:
            parts.extend(hn)
            sources.append("HN搜索")
    except Exception as e:  # noqa: BLE001
        logger.info("HN 搜索失败：%s", e)

    try:
        rd = _reddit_search(q)
        if rd:
            parts.extend(rd)
            sources.append("Reddit")
    except Exception as e:  # noqa: BLE001
        logger.info("Reddit 搜索失败：%s", e)

    # 去重保序
    seen: set[str] = set()
    uniq: list[str] = []
    for p in parts:
        key = p[:120]
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)

    return "\n---\n".join(uniq)[:limit], sources
