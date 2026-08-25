"""从 Greenhouse / Lever / Ashby 公开职位板按公司+标题找回申请链接。

CronJobs JobsBot 的岗位本来就从这些 ATS 吃进来；Discord 没登录时，
对得上的申请页就是原文。一对多或对不上就空着，不要猜。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (compatible; Scraper/1.0)"}
SKIP_COMPANIES = {
    "unknown", "未知", "nexthire", "jobsbot", "cronjobs", "various", "n/a",
}

_PAREN_RE = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def norm_title(value: str) -> str:
    text = _PAREN_RE.sub(" ", value or "")
    text = _NON_ALNUM_RE.sub(" ", text.lower())
    return " ".join(text.split())


def company_slugs(company: str) -> list[str]:
    raw = (company or "").strip()
    if not raw or raw.lower() in SKIP_COMPANIES:
        return []
    words = [w for w in _NON_ALNUM_RE.split(raw.lower()) if w]
    glued = "".join(words)
    out: list[str] = []
    if glued:
        out.append(glued)
    if words:
        out.append(words[0])
        if len(words) > 1:
            out.append("".join(words[:2]))
    skip = {"inc", "llc", "ltd", "co", "the", "corp", "company", "labs", "lab"}
    seen: set[str] = set()
    result: list[str] = []
    for slug in out:
        if slug in seen or slug in skip or len(slug) < 3:
            continue
        seen.add(slug)
        result.append(slug)
    return result


def _get_json(url: str) -> object | None:
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.loads(res.read())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def fetch_board_postings(slug: str) -> list[tuple[str, str]]:
    """返回 [(norm_title, url), ...]。"""
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs")
    if isinstance(data, dict) and data.get("jobs"):
        rows = []
        for job in data["jobs"]:
            url = str(job.get("absolute_url") or "").strip()
            title = norm_title(str(job.get("title") or ""))
            if url and title:
                rows.append((title, url[:512]))
        if rows:
            return rows

    data = _get_json(f"https://api.lever.co/v0/postings/{slug}")
    if isinstance(data, list) and data:
        rows = []
        for job in data:
            url = str(job.get("hostedUrl") or job.get("applyUrl") or "").strip()
            title = norm_title(str(job.get("text") or job.get("title") or ""))
            if url and title:
                rows.append((title, url[:512]))
        if rows:
            return rows

    data = _get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}")
    jobs = []
    if isinstance(data, dict):
        jobs = data.get("jobs") or data.get("jobPostings") or []
    if isinstance(jobs, list) and jobs:
        rows = []
        for job in jobs:
            if not isinstance(job, dict):
                continue
            url = str(job.get("jobUrl") or job.get("applyUrl") or "").strip()
            title = norm_title(str(job.get("title") or job.get("name") or ""))
            if url and title:
                rows.append((title, url[:512]))
        if rows:
            return rows
    return []


def match_url(title: str, postings: list[tuple[str, str]]) -> str:
    """只在规范化标题唯一命中时返回链接。"""
    needle = norm_title(title)
    if not needle:
        return ""
    hits = [url for post_title, url in postings if post_title == needle]
    if len(hits) == 1:
        return hits[0]
    if len(set(hits)) == 1 and hits:
        return hits[0]
    return ""


class BoardCache:
    def __init__(self, pause: float = 0.15):
        self.pause = pause
        self._slug_postings: dict[str, list[tuple[str, str]]] = {}
        self._company_postings: dict[str, list[tuple[str, str]]] = {}

    def postings_for(self, company: str) -> list[tuple[str, str]]:
        key = (company or "").strip().lower()
        if key in self._company_postings:
            return self._company_postings[key]
        for slug in company_slugs(company):
            if slug not in self._slug_postings:
                time.sleep(self.pause)
                self._slug_postings[slug] = fetch_board_postings(slug)
            if self._slug_postings[slug]:
                self._company_postings[key] = self._slug_postings[slug]
                return self._slug_postings[slug]
        self._company_postings[key] = []
        return []

    def lookup(self, company: str, title: str) -> str:
        return match_url(title, self.postings_for(company))
