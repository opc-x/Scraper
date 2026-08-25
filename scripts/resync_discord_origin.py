"""给 Discord 存量岗位补原文链接。

Discord 网页没登录时，走 Greenhouse/Lever/Ashby 公开职位板（JobsBot 的真正来源），
标题唯一命中才写。一对多或对不上就空着。

用法：
    python -m scripts.resync_discord_origin --dry-run
    python -m scripts.resync_discord_origin
"""

from __future__ import annotations

import argparse

from app.core.ats_lookup import BoardCache
from app.db.connection import SessionLocal
from app.db.schema import ScrapedJob


def main(dry_run: bool = False) -> None:
    if not SessionLocal:
        print("数据库未配置")
        return
    db = SessionLocal()
    cache = BoardCache()
    filled = skipped = 0
    companies_tried: set[str] = set()
    try:
        rows = (
            db.query(ScrapedJob)
            .filter(ScrapedJob.channel == "discord")
            .all()
        )
        missing = [row for row in rows if not (row.url or "").strip()]
        print(f"discord {len(rows)} 条，缺链接 {len(missing)}", flush=True)
        for row in missing:
            companies_tried.add(row.company or "")
            url = cache.lookup(row.company or "", row.title or "")
            if not url:
                skipped += 1
                continue
            filled += 1
            if not dry_run:
                row.url = url
                raw = dict(row.raw or {}) if isinstance(row.raw, dict) else {}
                raw["origin_refilled"] = "ats"
                row.raw = raw
            if filled % 25 == 0:
                print(f"  已命中 {filled}，未命中 {skipped}", flush=True)
        if dry_run:
            db.rollback()
        else:
            db.commit()
            from app.api.routes.scraped import invalidate_scraped_cache
            invalidate_scraped_cache()
        print(
            f"命中 {filled} 未命中 {skipped} 公司 {len(companies_tried)} "
            f"dry_run={dry_run}",
            flush=True,
        )
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    main(parser.parse_args().dry_run)
