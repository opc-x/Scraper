"""V2EX「酷工作」节点：公开 Atom feed，不需要 key、不需要登录态。

  https://www.v2ex.com/feed/jobs.xml

帖子是社区自发招聘贴（中英混杂，很多是老板/HR 直接发），没有结构化字段，
标题/正文里才有城市、薪资、技术栈这些信息，所以这里跟 jobboards.py 一个思路：
只做机械关键词过滤（排除明显非技术岗），不烧 LLM token，真正的"远程Java+简历匹配"
判断交给 scripts/score_jobs.py 里的本机 Claude 批量打分。
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx

from app.adapters.base import BaseAdapter
from app.core.models import Job, SearchRequest

logger = logging.getLogger(__name__)

FEED_URL = "https://www.v2ex.com/feed/jobs.xml"
NODE_URL = "https://www.v2ex.com/go/jobs?p={p}"
TOPIC_URL = "https://www.v2ex.com/t/{tid}"
TOPIC_API_URL = "https://www.v2ex.com/api/topics/show.json?id={tid}"
LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
H1_RE = re.compile(r"<h1>(.*?)</h1>", re.S)
TOPIC_CONTENT_RE = re.compile(r'<div class="topic_content">(.*?)</div>\s*</div>', re.S)
AGO_RE = re.compile(r'<span class="ago"[^>]*title="([^"]+)"')
DEFAULT_MAX_AGE_DAYS = 90
MAX_PAGES = 120
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126"}

# 中英混杂，标题判断要两套词表一起上。命中任一即认为可能是技术岗，
# 精确的"远程"“Java"判断留给批量打分脚本。
TECH_RE = re.compile(
    r"(java|python|golang|\bgo\b|rust|typescript|javascript|node\.?js|"
    r"engineer|developer|programmer|devops|sre|backend|frontend|full[- ]?stack|"
    r"architect|工程师|开发|后端|前端|全栈|架构师|程序员|技术|研发|算法|"
    r"数据|大数据|分布式|运维)",
    re.I,
)
NON_TECH_RE = re.compile(
    r"(bd|sales|销售|运营|市场|hr\b|招聘专员|猎头|中介|财务|会计|客服|行政|"
    r"设计师|ui/ux|产品经理(?!.*技术)|新媒体|自媒体|带货|搭梯子|翻墙)",
    re.I,
)

ENTRY_RE = re.compile(r"<entry>(.*?)</entry>", re.S)
FIELD_RE = {
    "title": re.compile(r"<title>(.*?)</title>", re.S),
    "link": re.compile(r'<link rel="alternate"[^>]*href="([^"]*)"'),
    "published": re.compile(r"<published>(.*?)</published>"),
    "author": re.compile(r"<name>(.*?)</name>"),
    "content": re.compile(r"<content[^>]*>(.*?)</content>", re.S),
}


def _text(raw: str) -> str:
    t = raw or ""
    if "<![CDATA[" in t:
        t = t.split("<![CDATA[", 1)[1].rsplit("]]>", 1)[0]
    t = html.unescape(t)
    t = re.sub(r"<br\s*/?>|</p>|</div>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _is_tech(title: str, content: str) -> bool:
    blob = f"{title} {content[:300]}"
    return bool(TECH_RE.search(blob)) and not NON_TECH_RE.search(title)


def _city(title: str) -> str:
    m = re.match(r"^\s*[\[【]([^\]】]+)[\]】]", title)
    return m.group(1)[:64] if m else ""


class V2exAdapter(BaseAdapter):
    """V2EX 酷工作节点，公开 Atom feed 直接拉，`search()` 走内存关键词过滤。"""

    name = "v2ex"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    def _c(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(follow_redirects=True)
        return self._client

    async def fetch_all(self) -> list[Job]:
        client = self._c()
        try:
            r = await client.get(FEED_URL, headers=UA, timeout=30)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            logger.warning("V2EX feed 拉取失败: %s", e)
            return []

        jobs: list[Job] = []
        for block in ENTRY_RE.findall(r.text):
            def field(key: str) -> str:
                m = FIELD_RE[key].search(block)
                return m.group(1) if m else ""

            link = field("link")
            if not link:
                continue
            title = _text(field("title"))
            content = _text(field("content"))
            if not _is_tech(title, content):
                continue
            jobs.append(Job(
                channel="v2ex",
                external_id=link.rsplit("/t/", 1)[-1].split("#")[0][:128],
                title=title[:250],
                company=field("author")[:250] or "未知",
                salary="",
                city=_city(title),
                skills=[],
                description=content[:4000],
                url=link[:512],
                raw={
                    "source": "v2ex",
                    "published": field("published"),
                    "is_remote": bool(re.search(r"remote|远程", title + content, re.I)),
                    "has_apply_link": True,
                },
            ))
        return jobs

    def _parse_node_items(self, html_text: str) -> list[dict]:
        items: list[dict] = []
        for block in LD_JSON_RE.findall(html_text or ""):
            try:
                data = json.loads(html.unescape(block))
            except json.JSONDecodeError:
                continue
            elements = (data.get("mainEntity") or {}).get("itemListElement") or []
            for element in elements:
                post = element.get("item") or {}
                url = str(post.get("url") or "")
                if "/t/" not in url:
                    continue
                tid = url.rsplit("/t/", 1)[-1].split("?")[0].split("#")[0]
                published = post.get("datePublished") or ""
                dt = None
                if published:
                    try:
                        dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                    except ValueError:
                        dt = None
                items.append({
                    "tid": tid,
                    "title": str(post.get("headline") or ""),
                    "published": published,
                    "dt": dt,
                })
            if items:
                break
        return items

    async def _fetch_topic_job(self, item: dict) -> Job | None:
        tid = item["tid"]
        try:
            # 详情 HTML 高频访问容易触发整站 403；公开 v1 API 返回同一主题正文且更稳定。
            r = await self._c().get(TOPIC_API_URL.format(tid=tid), headers=UA, timeout=30)
            r.raise_for_status()
            payload = r.json()
            topic = payload[0] if isinstance(payload, list) and payload else {}
        except Exception as e:  # noqa: BLE001
            logger.warning("V2EX topic %s 拉取失败: %s", tid, e)
            return None
        title = str(topic.get("title") or item["title"])
        content = str(topic.get("content") or "")
        posted = topic.get("created") or item["published"]
        member = topic.get("member") if isinstance(topic.get("member"), dict) else {}
        city = _city(title)
        return Job(
            channel="v2ex",
            external_id=tid,
            title=title[:250],
            company=str(member.get("username") or "未知")[:250],
            salary="",
            city=city,
            skills=[],
            description=content[:12000],
            url=TOPIC_URL.format(tid=tid),
            raw={
                "source": "v2ex",
                "published": posted,
                "posted_at": posted,
                "is_remote": bool(re.search(r"remote|远程", title + content, re.I)),
                "has_apply_link": True,
            },
        )

    async def fetch_java_recent(self, *, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> list[Job]:
        """拉取酷工作节点近 N 天的完整候选集。

        这里禁止提前复制入库规则（以前先用 java_in_title 截断，导致规则后台改了也
        看不到被截掉的帖子）。方向、远程、低英语、时效等条件统一由 persist 的
        evaluate_ingest_gate 裁定；adapter 只负责覆盖数据源和解析正文。
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        seen: set[str] = set()
        recent_items: list[dict] = []
        for page in range(1, MAX_PAGES + 1):
            try:
                r = await self._c().get(NODE_URL.format(p=page), headers=UA, timeout=30)
                r.raise_for_status()
            except Exception as e:  # noqa: BLE001
                logger.warning("V2EX 节点第 %s 页失败: %s", page, e)
                break
            rows = self._parse_node_items(r.text)
            if not rows:
                break
            in_window = False
            for row in rows:
                tid = row["tid"]
                if tid in seen:
                    continue
                seen.add(tid)
                dt = row["dt"]
                if dt is not None and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                    row["dt"] = dt
                if dt and dt < cutoff:
                    continue
                in_window = True
                recent_items.append(row)
            if page > 1 and not in_window:
                break
        # 90 天可能有上千帖；有限并发抓正文，避免串行耗时，也避免压垮 V2EX。
        semaphore = asyncio.Semaphore(4)

        async def fetch_one(item: dict) -> Job | None:
            async with semaphore:
                return await self._fetch_topic_job(item)

        rows = await asyncio.gather(*(fetch_one(item) for item in recent_items))
        return [job for job in rows if job is not None]

    async def search(self, req: SearchRequest) -> list[Job]:
        jobs = await self.fetch_all()
        kw = (req.keyword or "").strip().lower()
        if not kw:
            return jobs
        return [
            j for j in jobs
            if kw in f"{j.title} {j.company} {j.description[:600]}".lower()
        ]

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
