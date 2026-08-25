"""远程招聘站渠道：RemoteOK + WeWorkRemotely。

这两家都提供公开数据源，不需要 key、不需要登录态、不需要浏览器：
  - RemoteOK        https://remoteok.com/api          一次 100 条，字段已结构化
  - WeWorkRemotely  分类 RSS，每个分类 25 条，全是技术岗

跟 telegram/x 那种要 LLM 抽取的渠道不同，这里字段是现成的，不烧 token。
`search()` 走内存过滤，批量入库走 scripts/mine_job_boards.py。
"""

from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime

import httpx

from app.adapters.base import BaseAdapter
from app.core.models import Job, SearchRequest

logger = logging.getLogger(__name__)

REMOTEOK_API = "https://remoteok.com/api"
# 不带参数只返回最新 100 条混合岗位（技术岗占比很低），
# 按 tag 拉每个标签各 100 条，去重后量级差一个数量级
REMOTEOK_TAGS = [
    "dev", "python", "javascript", "typescript", "java", "golang", "rust",
    "node", "react", "backend", "devops", "aws", "kubernetes", "machine-learning",
    "ai", "data", "senior", "engineer",
    # 冲量：跟简历方向沾边的都拉一遍
    "scala", "kotlin", "spring", "microservices", "distributed-systems",
    "big-data", "hadoop", "spark", "kafka", "elasticsearch", "sql", "postgres",
    "redis", "docker", "cloud", "architect", "lead", "api", "sre", "platform",
    "infrastructure", "security", "blockchain", "web3", "fintech", "saas",
]
WWR_RSS = "https://weworkremotely.com/categories/{cat}.rss"
WWR_CATEGORIES = [
    "remote-jobs",                      # 全站，量最大
    "remote-programming-jobs",
    "remote-back-end-programming-jobs",
    "remote-front-end-programming-jobs",
    "remote-full-stack-programming-jobs",
    "remote-devops-sysadmin-jobs",
    "remote-management-and-finance-jobs",   # 里面混着 engineering manager
    "remote-product-jobs",
]
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126"}

# 两家都混了大量非技术岗（保安、店长、销售、市场），而且 RemoteOK 的 tags 很脏
# （店长岗也能带上 dev 标签），所以只认标题，不看 tags 和描述。
ROLE_RE = re.compile(
    r"\b("
    r"java|engineer|engineering|developer|programmer|coder|разработчик|programador|"
    r"devops|sre|site reliability|platform|infrastructure|"
    r"back[- ]?end|front[- ]?end|full[- ]?stack|"
    r"software architect|solutions architect|cloud architect|data architect|"
    r"data scientist|data engineer|machine learning|ml engineer|ai engineer|"
    r"llm|mlops|qa engineer|test engineer|automation engineer|"
    r"ios developer|android developer|mobile engineer|"
    r"security engineer|blockchain|smart contract|"
    r"cto|tech lead|technical lead|staff engineer|principal engineer"
    r")\b|工程师|开发",
    re.I,
)
# 命中这些一律排除，优先级高于 ROLE_RE（"Security Guard" 别被 security 带进来）
NON_TECH_RE = re.compile(
    r"\b(nurse|practitioner|physician|specimen|collector|driver|caregiver|therapist|"
    r"dental|pharmacy|teacher|tutor|barista|cleaner|warehouse|guard|store manager|"
    r"sales|marketing|paid media|gtm|account executive|customer success|recruiter|"
    r"copywriter|social media|community manager|bookkeep|accountant|paralegal)\b", re.I)


def _strip(t: str) -> str:
    """RSS 里的描述是被转义过的 HTML，必须先反转义再剥标签，
    否则 &lt;p&gt; 反转义之后又变回 <p> 留在正文里。"""
    t = html.unescape(t or "")
    t = re.sub(r"<br\s*/?>|</p>|</div>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = html.unescape(t)  # 有些源是双重转义（&amp;nbsp;）
    t = t.replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _is_tech(title: str) -> bool:
    """只按岗位标题判断 —— 描述里出现 python 不代表这是个工程岗。"""
    return bool(ROLE_RE.search(title)) and not NON_TECH_RE.search(title)


def _salary_text(lo, hi) -> str:
    lo, hi = int(lo or 0), int(hi or 0)
    if not hi:
        return ""
    if lo and lo != hi:
        return f"${lo:,} - ${hi:,}"
    return f"${hi:,}"


async def fetch_remoteok(client: httpx.AsyncClient, tags: list[str] | None = None) -> list[Job]:
    rows: list[dict] = []
    seen_ids: set[str] = set()
    for tag in [None, *(tags if tags is not None else REMOTEOK_TAGS)]:
        params = {"tag": tag} if tag else None
        try:
            r = await client.get(REMOTEOK_API, headers=UA, params=params, timeout=30)
            r.raise_for_status()
            payload = r.json()
        except Exception as e:  # noqa: BLE001
            logger.warning("RemoteOK tag=%s 拉取失败: %s", tag, e)
            continue
        for row in payload:
            if not isinstance(row, dict) or not row.get("position"):
                continue
            rid = str(row.get("id") or row.get("slug") or row.get("url", ""))
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            rows.append(row)

    jobs: list[Job] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("position"):
            continue
        tags = row.get("tags") or []
        if not _is_tech(str(row.get("position", ""))):
            continue
        jobs.append(Job(
            channel="remoteok",
            external_id=str(row.get("id") or row.get("slug") or row.get("url", ""))[:128],
            title=str(row.get("position", ""))[:250],
            company=str(row.get("company") or "未知")[:250],
            salary=_salary_text(row.get("salary_min"), row.get("salary_max"))[:64],
            city=(row.get("location") or "Remote")[:64],
            skills=[str(t)[:40] for t in tags][:12],
            description=_strip(row.get("description", ""))[:4000],
            url=(row.get("url") or row.get("apply_url") or "")[:512],
            raw={
                "source": "remoteok",
                "date": row.get("date"),
                "tags": tags,
                "is_remote": True,
                "has_apply_link": bool(row.get("url") or row.get("apply_url")),
            },
        ))
    return jobs


ITEM_RE = re.compile(r"<item>(.*?)</item>", re.S)
TAG_RE = {
    k: re.compile(rf"<{k}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{k}>", re.S)
    for k in ("title", "link", "description", "pubDate", "region", "category")
}


def _rss_field(block: str, key: str) -> str:
    m = TAG_RE[key].search(block)
    return _strip(m.group(1)) if m else ""


def _wwr_url(cat: str) -> str:
    if cat == "remote-jobs":
        return "https://weworkremotely.com/remote-jobs.rss"
    return WWR_RSS.format(cat=cat)


async def fetch_wwr(client: httpx.AsyncClient, categories: list[str] | None = None) -> list[Job]:
    jobs: list[Job] = []
    seen: set[str] = set()
    for cat in (categories or WWR_CATEGORIES):
        try:
            r = await client.get(_wwr_url(cat), headers=UA, timeout=30)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            logger.warning("WWR %s 拉取失败: %s", cat, e)
            continue
        for block in ITEM_RE.findall(r.text):
            link = _rss_field(block, "link")
            if not link or link in seen:
                continue
            seen.add(link)
            raw_title = _rss_field(block, "title")
            # WWR 的标题格式是 "公司: 岗位"
            company, _, title = raw_title.partition(":")
            if not title:
                company, title = "未知", raw_title
            desc = _rss_field(block, "description")
            if not _is_tech(title):
                continue
            jobs.append(Job(
                channel="weworkremotely",
                external_id=link.rstrip("/").rsplit("/", 1)[-1][:128],
                title=title.strip()[:250],
                company=company.strip()[:250],
                salary="",
                city=(_rss_field(block, "region") or "Remote")[:64],
                skills=[],
                description=desc[:4000],
                url=link[:512],
                raw={
                    "source": "weworkremotely",
                    "category": cat,
                    "posted_at": _rss_field(block, "pubDate"),
                    "is_remote": True,
                    "has_apply_link": True,
                },
            ))
    return jobs


class JobBoardAdapter(BaseAdapter):
    """RemoteOK + WeWorkRemotely 合成渠道。两家都没有搜索接口，
    所以 search() 是先全量拉再按关键词内存过滤 —— 数据量就几百条，够用。"""

    name = "jobboards"

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    def _c(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(follow_redirects=True)
        return self._client

    async def fetch_all(self) -> list[Job]:
        client = self._c()
        jobs: list[Job] = []
        try:
            jobs += await fetch_remoteok(client)
        except Exception as e:  # noqa: BLE001
            logger.warning("RemoteOK 拉取失败: %s", e)
        jobs += await fetch_wwr(client)
        return jobs

    async def search(self, req: SearchRequest) -> list[Job]:
        jobs = await self.fetch_all()
        kw = (req.keyword or "").strip().lower()
        if not kw:
            return jobs
        return [
            j for j in jobs
            if kw in f"{j.title} {j.company} {' '.join(j.skills)} {j.description[:600]}".lower()
        ]

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
