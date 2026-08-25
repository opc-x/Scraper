"""把离线挖掘结果导入数据库。

HN 的每一条是职位，写 scraped_jobs；Telegram、Discord、X 是信源账号，
写 mined_accounts。重复运行会走现有 upsert，可安全续跑。
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.models import Job
from app.db.persist import persist_mined_accounts, persist_scraped_jobs

DATA = Path("data")


def load(name: str) -> list[dict]:
    path = DATA / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def import_hn(rows: list[dict]) -> None:
    jobs = [
        Job(
            channel="hackernews",
            external_id=f"hn_{row['post_id']}",
            title=row.get("role") or row.get("headline") or "Remote role",
            company=row.get("company") or "未知",
            salary="",
            city="Remote" if row.get("is_remote") else "",
            skills=row.get("stack", []),
            description=row.get("body", ""),
            url=row.get("url", ""),
            raw=row,
        )
        for row in rows
    ]
    persist_scraped_jobs(jobs)


def source_account(row: dict, channel: str) -> dict:
    handle = row.get("username") or row.get("vanity_code") or row.get("handle")
    score = row.get("prescreen") or min(100, 40 + row.get("job_score", 0) * 8)
    return {
        "handle": handle,
        "profile_url": row.get("url") or row.get("invite_url") or row.get("profile_url", ""),
        "bio": row.get("description") or row.get("bio") or row.get("note", ""),
        "confidence": score,
        "value_score": score,
        "kept": True,
        "tags": [channel, "remote_hiring"],
        "rationale": "公开信源发现脚本验活并通过关键词初筛",
    }


def main() -> None:
    import_hn(load("hn_hiring.json"))
    for channel, filename in (
        ("telegram", "telegram_job_channels.json"),
        ("discord", "discord_servers.json"),
        ("x", "x_hiring_accounts.json"),
    ):
        accounts = [source_account(row, channel) for row in load(filename)]
        persist_mined_accounts(channel, "remote_hiring", accounts)
        print(f"[db] {channel}: {len(accounts)}")
    print(f"[db] hackernews: {len(load('hn_hiring.json'))}")


if __name__ == "__main__":
    main()
