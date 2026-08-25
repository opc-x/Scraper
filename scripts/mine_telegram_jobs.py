"""把 Telegram 招聘频道的历史帖子抓成岗位，写入 scraped_jobs。

免登录：公开频道网页预览 t.me/s/<name> 每页 ~20 条，靠 ?before=<msg_id> 往前翻历史。
频道清单来自 data/telegram_job_channels.json（mine_telegram_job_channels.py 的产出）。

用法：
    python -m scripts.mine_telegram_jobs --pages 15          # 每个频道往前翻 15 页
    python -m scripts.mine_telegram_jobs --channels remotejobs,llm_jobs
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/126"}
SRC = Path("data/telegram_job_channels.json")
OUT = Path("data/telegram_jobs.json")

MSG_BLOCK_RE = re.compile(
    r'<div class="tgme_widget_message[^"]*"[^>]*data-post="([^"]+)"(.*?)(?=<div class="tgme_widget_message |</section>)',
    re.S,
)
TEXT_RE = re.compile(r'<div class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)
TIME_RE = re.compile(r'<time[^>]*datetime="([^"]+)"')
HREF_RE = re.compile(r'href="(https?://[^"]+)"')

# 招聘帖 vs 求职/闲聊：得同时命中岗位词和招聘动作词才算
ROLE_RE = re.compile(
    r"\b(engineer|developer|programmer|architect|devops|sre|data scientist|analyst|"
    r"designer|qa|tester|pm|product manager|lead|cto)\b", re.I)
HIRING_RE = re.compile(
    r"\b(hiring|we[' ]?re hiring|job|vacancy|position|opening|apply|role|"
    r"looking for|join (our|the) team|ищем|вакансия|требуется)\b", re.I)
SEEKING_RE = re.compile(
    r"\b(looking for (a |an )?(job|work|position|opportunity)|open to work|available for hire|"
    r"i am a |i'm a |my portfolio|hire me|#forhire|ищу работу|резюме)\b", re.I)

SALARY_RE = re.compile(
    r"(?:[$€£]\s?\d[\d,.]*\s?(?:k|K)?(?:\s?[-–—to]+\s?[$€£]?\s?\d[\d,.]*\s?(?:k|K)?)?"
    r"(?:\s?(?:per|/)\s?(?:year|yr|month|mo|hour|hr|week))?)"
    r"|(?:\d[\d,.]*\s?[-–—]\s?\d[\d,.]*\s?(?:USD|EUR|GBP)\b)")
REMOTE_RE = re.compile(r"\bremote\b|\bworldwide\b|\bwork from home\b|удал[её]н", re.I)
LOC_RE = re.compile(
    r"\b(worldwide|global|anywhere|US|USA|United States|EU|Europe|UK|Canada|LATAM|"
    r"APAC|Asia|Germany|Poland|Portugal|Spain|India|Remote)\b")

SKILLS = [
    "Node.js", "Nodejs", "Node", "JavaScript", "TypeScript", "Python", "Django", "FastAPI",
    "Flask", "Java", "Spring", "Kotlin", "Go", "Golang", "Rust", "C++", "C#", ".NET", "PHP",
    "Laravel", "Ruby", "Rails", "React", "Vue", "Angular", "Svelte", "Next.js", "Nest",
    "AWS", "GCP", "Azure", "Kubernetes", "Docker", "Terraform", "PostgreSQL", "MySQL",
    "MongoDB", "Redis", "Kafka", "GraphQL", "LLM", "RAG", "LangChain", "AI agent", "Agent",
    "PyTorch", "TensorFlow", "MLOps", "Solidity", "Web3",
]
SPAM_RE = re.compile(r"\b(casino|betting|porn|投资|加微信|刷单|forex signal)\b", re.I)


def fix_mojibake(t: str) -> str:
    """部分频道的帖子源数据本身就是双重编码的（em dash 变成 â€"），能修则修。"""
    if "Ã" not in t and "â" not in t:
        return t
    try:
        return t.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return t


def strip_tags(t: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", t or "")
    t = re.sub(r"</p>|</div>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    return fix_mojibake(html.unescape(re.sub(r"\n{3,}", "\n\n", t))).strip()


def fetch(url: str, retries: int = 2) -> str | None:
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read().decode("utf-8", "ignore")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
            if i == retries - 1:
                return None
            time.sleep(1.5)
    return None


def parse_page(body: str) -> tuple[list[dict], str | None]:
    """返回 (这一页的消息, 最老那条的 msg_id 用于继续往前翻)。"""
    msgs = []
    oldest = None
    for post, block in MSG_BLOCK_RE.findall(body):
        m = TEXT_RE.search(block)
        if not m:
            continue
        text = strip_tags(m.group(1))
        if len(text) < 40:
            continue
        t = TIME_RE.search(block)
        links = [u for u in HREF_RE.findall(block) if "t.me/" not in u and "telegram.org" not in u]
        msgs.append({
            "post": post,                       # 形如 channel/12345
            "url": f"https://t.me/{post}",
            "posted_at": t.group(1) if t else "",
            "text": text,
            "links": links[:5],
        })
        mid = post.rsplit("/", 1)[-1]
        if mid.isdigit() and (oldest is None or int(mid) < int(oldest)):
            oldest = mid
    return msgs, oldest


def is_job(text: str) -> bool:
    if SPAM_RE.search(text):
        return False
    if SEEKING_RE.search(text) and not HIRING_RE.search(text):
        return False  # 求职自荐帖，不是招聘
    return bool(ROLE_RE.search(text) and HIRING_RE.search(text))


# 这些频道的帖子多是带标签的结构化文本，先按字段抠，抠不到再退回启发式
FIELD_PATTERNS = {
    "title": r"(?:^|\n)\s*(?:🚀\s*)?(?:Title|Position|Job title|Role|Vacancy)\s*[:：]\s*(.+)",
    "company": r"(?:^|\n)\s*(?:🏢\s*)?(?:Company(?: name)?|Employer)\s*[:：]\s*(.+)",
    "salary": r"(?:^|\n)\s*(?:💰\s*)?(?:Salary|Compensation|Pay|Rate)\s*[:：]\s*(.+)",
    "city": r"(?:^|\n)\s*(?:📍\s*)?(?:Location|Locations?|Region|Where)\s*[:：]\s*(.+)",
    "experience": r"(?:^|\n)\s*(?:Grades?|Level|Seniority|Experience)\s*[:：]\s*(.+)",
}
# 纯装饰性的横幅行，不能当标题
BANNER_RE = re.compile(
    r"^(?:[\W_]*)(job opportunity|new job|vacancy|hiring|job alert|we are hiring|"
    r"remote job|job post|new vacancy|position open)[\W_]*$", re.I)


def field(text: str, key: str) -> str:
    m = re.search(FIELD_PATTERNS[key], text, re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:250] if m else ""


def guess_title(text: str) -> str:
    """标签抠不到时：跳过横幅/标签行，取第一条像岗位名的行。"""
    for ln in text.split("\n"):
        ln = re.sub(r"^[\W_]+|[\W_]+$", "", ln).strip()
        if len(ln) < 6 or BANNER_RE.match(ln) or ln.startswith("#"):
            continue
        if re.match(r"^(published|tags?|apply|ready to apply|forbidden|anywhere|remote)\b", ln, re.I):
            continue
        return ln[:200]
    return ""


def to_job(msg: dict, channel_name: str) -> dict:
    text = msg["text"]

    title = field(text, "title") or guess_title(text) or "Telegram 招聘帖"
    company = field(text, "company")
    if not company:
        m = re.search(r"(?:at|@)\s+([A-Z][\w .&\'-]{2,40})", text)
        company = m.group(1).strip() if m else ""

    salary = field(text, "salary")
    if not salary:
        sm = SALARY_RE.search(text)
        salary = sm.group(0).strip() if sm else ""

    loc_field = field(text, "city")
    locs = [x for x in dict.fromkeys(LOC_RE.findall(text))][:3]
    remote = bool(REMOTE_RE.search(text)) or bool(re.search(r"Remote\s*[:：]\s*Yes", text, re.I))
    city = loc_field or ("Remote" if remote else (locs[0] if locs else ""))

    skills = [s for s in SKILLS if re.search(rf"\b{re.escape(s)}\b", text, re.I)]
    # 频道自己的 t.me 链接不算申请入口，优先取帖子里的外链
    apply_url = msg["links"][0] if msg["links"] else msg["url"]

    return {
        "channel": "telegram",
        "external_id": hashlib.md5(msg["post"].encode()).hexdigest()[:24],
        "title": title[:250],
        "company": (company or "未知")[:250],
        "salary": salary[:64],
        "city": city[:64],
        "experience": field(text, "experience")[:64],
        "education": "",
        "skills": sorted(set(skills))[:12],
        "description": text[:4000],
        "url": apply_url[:512],
        "raw": {
            "source_channel": channel_name,
            "post": msg["post"],
            "posted_at": msg["posted_at"],
            "post_url": msg["url"],
            "links": msg["links"],
            "regions": locs,
            "is_remote": remote,
            "has_apply_link": not apply_url.startswith("https://t.me/"),
        },
    }


def crawl_channel(name: str, pages: int) -> list[dict]:
    jobs, before, seen = [], None, set()
    for _ in range(pages):
        url = f"https://t.me/s/{name}" + (f"?before={before}" if before else "")
        body = fetch(url)
        if not body:
            break
        msgs, oldest = parse_page(body)
        if not msgs or oldest is None or oldest in seen:
            break
        seen.add(oldest)
        for m in msgs:
            if is_job(m["text"]):
                jobs.append(to_job(m, name))
        before = oldest
        time.sleep(0.2)
    return jobs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=15, help="每个频道往前翻多少页（每页约 20 条）")
    ap.add_argument("--channels", default="", help="逗号分隔，只跑这些频道；默认跑全部")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--no-db", action="store_true")
    args = ap.parse_args()

    if args.channels:
        names = [c.strip() for c in args.channels.split(",") if c.strip()]
    else:
        names = [c["username"] for c in json.loads(SRC.read_text(encoding="utf-8"))]
    print(f"[tg] {len(names)} 个频道 × 最多 {args.pages} 页", file=sys.stderr)

    all_jobs: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for name, jobs in zip(names, pool.map(lambda n: crawl_channel(n, args.pages), names)):
            all_jobs.extend(jobs)
            print(f"  @{name}: {len(jobs)} 条招聘帖", file=sys.stderr)

    dedup = {j["external_id"]: j for j in all_jobs}
    rows = list(dedup.values())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[tg] 去重后 {len(rows)} 条 -> {OUT}", file=sys.stderr)

    if args.no_db:
        return
    from app.core.models import Job
    from app.db.persist import persist_scraped_jobs
    persist_scraped_jobs([Job(**r) for r in rows], lens_only=True)
    print(f"[tg] 已写入 scraped_jobs", file=sys.stderr)


if __name__ == "__main__":
    main()
