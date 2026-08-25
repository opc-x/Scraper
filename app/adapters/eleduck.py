"""电鸭公开招聘频道适配器。

通过站点公开 JSON API 抓取近 90 天招聘；无需登录。这里只做技术岗位的
机械预筛，个人的 Java/Agent、Remote/杭州及语言环境门禁仍由统一规则处理。
"""

from __future__ import annotations

import asyncio
import html
import logging
import re
from datetime import datetime, timedelta, timezone

import httpx

from app.adapters.base import BaseAdapter
from app.core.models import Job, SearchRequest

logger = logging.getLogger(__name__)

API_ROOT = "https://svc.eleduck.com/api/v1"
SITE_ROOT = "https://eleduck.com"
DEFAULT_MAX_AGE_DAYS = 90
DEFAULT_MIN_JOBS = 150
PAGE_SIZE = 25
UA = {"User-Agent": "JobSniper/1.0 (+https://eleduck.com/)"}

TECH_RE = re.compile(
    r"(java|jvm|spring|kotlin|scala|python|golang|\bgo\b|rust|c\+\+|\.net|"
    r"typescript|javascript|node\.?js|react|vue|android|ios|flutter|uniapp|"
    r"engineer|developer|devops|sre|backend|frontend|full[- ]?stack|data|ai|"
    r"llm|agent|机器学习|人工智能|大模型|智能体|算法|工程师|开发|后端|前端|"
    r"全栈|架构|研发|程序员|运维|测试|数据)",
    re.I,
)
NON_TECH_TITLE_RE = re.compile(
    r"(销售|客服|行政|财务|会计|人事|猎头|招聘专员|主播|剪辑师|设计师|"
    r"产品经理|运营|市场|商务|投放|文案|翻译|录入|渠道合作|用户研究)",
    re.I,
)
SALARY_RE = re.compile(
    r"(?:¥|￥|\$|USD\s*)?\d+(?:\.\d+)?\s*(?:[kKwW万千元]|U|USD|RMB)?\s*"
    r"(?:[-–—~至到]\s*(?:¥|￥|\$|USD\s*)?\d+(?:\.\d+)?\s*)?"
    r"(?:[kKwW万千元]|U|USD|RMB)"
    r"(?:\s*/\s*(?:月|天|日|小时|时))?",
    re.I,
)


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _plain_text(value: str) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<br\s*/?>|</p>|</li>|</h[1-6]>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _tag_map(post: dict) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for tag in post.get("tags") or []:
        code = (tag.get("tag_group") or {}).get("code", "")
        result.setdefault(code, []).append(tag.get("name", ""))
    return result


def _is_technical(post: dict) -> bool:
    tags = _tag_map(post)
    if any(x in {"开发", "AI工程师", "运维"} for x in tags.get("skill_type", [])):
        return True
    title = post.get("full_title") or post.get("title") or ""
    summary = post.get("summary") or ""
    return bool(TECH_RE.search(f"{title} {summary[:800]}")) and not NON_TECH_TITLE_RE.search(title)


def _post_url(post: dict) -> str:
    category_code = (post.get("category") or {}).get("code")
    prefix = "tposts" if category_code == "talent" else "posts"
    return f"{SITE_ROOT}/{prefix}/{post['id']}"


def _to_job(post: dict) -> Job:
    tags = _tag_map(post)
    description = _plain_text(
        post.get("content") or post.get("raw_content") or post.get("summary", "")
    )
    title = post.get("full_title") or post.get("title") or ""
    blob = f"{title}\n{description}"
    salary_match = SALARY_RE.search(blob)
    city_names = tags.get("city", [])
    work_modes = tags.get("job_type", [])
    is_remote = any("远程" in x or "线上" in x for x in work_modes) or bool(
        re.search(r"\bremote\b|远程|居家办公", blob, re.I)
    )
    skills = [x for x in tags.get("skill_type", []) if x]
    skills.extend(sorted({m.group(0) for m in TECH_RE.finditer(blob[:4000])}, key=str.lower)[:20])
    author = post.get("user") or {}
    published_at = post.get("published_at", "")
    return Job(
        channel="eleduck",
        external_id=str(post["id"]),
        title=title[:250],
        company=(author.get("nickname") or "电鸭社区招聘方")[:250],
        salary=salary_match.group(0).strip() if salary_match else "",
        city=("、".join(city_names) or ("远程" if is_remote else ""))[:128],
        skills=list(dict.fromkeys(skills)),
        description=description[:12000],
        url=_post_url(post),
        raw={
            "source": "eleduck",
            "posted_at": published_at,
            "published_at": published_at,
            "is_remote": is_remote,
            "has_apply_link": True,
            "category": (post.get("category") or {}).get("code", ""),
            "status": post.get("status", ""),
            "tags": post.get("tags") or [],
        },
    )


class EleduckAdapter(BaseAdapter):
    name = "eleduck"

    def __init__(self, client: httpx.AsyncClient | None = None):
        self._client = client
        self._owns_client = client is None

    def _c(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(headers=UA, follow_redirects=True, timeout=30)
        return self._client

    async def _get_json(self, path: str, params: dict | None = None) -> dict:
        last_error: Exception | None = None
        for attempt in range(4):
            try:
                response = await self._c().get(f"{API_ROOT}{path}", params=params)
                response.raise_for_status()
                return response.json()
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as exc:
                last_error = exc
                if attempt < 3:
                    await asyncio.sleep(2**attempt)
        assert last_error is not None
        raise last_error

    async def fetch_recent(
        self,
        *,
        max_age_days: int = DEFAULT_MAX_AGE_DAYS,
        min_jobs: int = DEFAULT_MIN_JOBS,
        fetch_details: bool = False,
        java_title_only: bool = False,
    ) -> list[Job]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
        candidates: dict[str, dict] = {}
        page = 1

        while True:
            payload = await self._get_json(
                "/jobs_channel/posts",
                {"page": page, "sort": "-published_at", "talent_included": "true"},
            )
            posts = payload.get("posts") or []
            if not posts:
                break
            oldest: datetime | None = None
            for post in posts:
                published = _parse_time(post.get("published_at", ""))
                if published and (oldest is None or published < oldest):
                    oldest = published
                if (
                    published
                    and published >= cutoff
                    and not post.get("closed")
                    and _is_technical(post)
                ):
                    candidates[str(post["id"])] = post

            pager = payload.get("pager") or {}
            reached_cutoff = oldest is not None and oldest < cutoff
            last_page = int(pager.get("pages") or pager.get("total_pages") or page)
            if reached_cutoff or page >= last_page:
                break
            page += 1

        if java_title_only:
            from app.core.job_derive import java_in_title

            candidates = {
                pid: post for pid, post in candidates.items()
                if java_in_title(post.get("full_title") or post.get("title") or "")
            }

        if min_jobs and len(candidates) < min_jobs:
            raise RuntimeError(
                f"电鸭近 {max_age_days} 天仅找到 {len(candidates)} 条技术职位，"
                f"低于要求的 {min_jobs} 条"
            )

        if not fetch_details:
            return [_to_job(post) for post in candidates.values()]

        jobs: list[Job] = []
        for post_id, summary in candidates.items():
            try:
                detail = (await self._get_json(f"/posts/{post_id}")).get("post") or summary
                jobs.append(_to_job(detail))
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("电鸭职位 %s 详情抓取失败，使用列表摘要: %s", post_id, exc)
                jobs.append(_to_job(summary))
        return jobs

    async def search(self, req: SearchRequest) -> list[Job]:
        jobs = await self.fetch_recent()
        keyword = (req.keyword or "").strip().lower()
        if not keyword:
            return jobs
        return [
            job
            for job in jobs
            if keyword in f"{job.title} {job.company} {job.description}".lower()
        ]

    async def close(self):
        if self._client and self._owns_client:
            await self._client.aclose()
        self._client = None
