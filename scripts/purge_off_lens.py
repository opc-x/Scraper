"""删掉不满足「Java + 远程 + 低英语要求 + 居家可应聘」的职位。

这是个人求职口径，不是通用基础设施规则。不满足的就是噪音，连 marks / 画像一起清。

用法：
    python -m scripts.purge_off_lens --dry-run
    python -m scripts.purge_off_lens
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from sqlalchemy import text

from app.core.job_derive import matches_target_lens
from app.db.connection import SessionLocal
from app.db.schema import ScrapedJob

RELATED_TABLES = ("job_marks", "job_profiles", "job_quality_reports", "job_value_tags")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not SessionLocal:
        raise SystemExit("数据库未配置")

    db = SessionLocal()
    try:
        rows = db.query(ScrapedJob).all()
        keep_ids = {row.id for row in rows if matches_target_lens(row)}
        doomed = [row for row in rows if row.id not in keep_ids]
        keep_n = len(keep_ids)
        by_ch = Counter(row.channel for row in doomed)
        print(
            f"总共 {len(rows)} 条，保留 {keep_n}，删除 {len(doomed)} {dict(by_ch)}",
            file=sys.stderr,
        )
        for row in doomed[:12]:
            print(f"  drop [{row.channel}] {row.title[:70]}", file=sys.stderr)
        if args.dry_run:
            return
        ids = [row.id for row in doomed]
        related_n = 0
        for i in range(0, len(ids), 400):
            chunk = ids[i:i + 400]
            db.query(ScrapedJob).filter(ScrapedJob.id.in_(chunk)).delete(synchronize_session=False)
            print(f"  已删 {min(i + 400, len(ids))}/{len(ids)}", flush=True)
        for table in RELATED_TABLES:
            result = db.execute(text(
                f"DELETE FROM {table} WHERE (channel, external_id) NOT IN "
                f"(SELECT channel, external_id FROM scraped_jobs)"
            ))
            related_n += result.rowcount or 0
        db.commit()
        from app.api.routes.scraped import invalidate_scraped_cache
        invalidate_scraped_cache()
        print(f"删除完成 {len(doomed)} 条职位 + {related_n} 条关联，剩余 {keep_n}", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
