"""一次性回填存量 scraped_jobs 的衍生字段（core_tags/is_remote/value_score 等）。

读接口改成只读这些列之后，跑一次这个脚本，不然存量数据全是列默认值（跟实际内容对不上）。
新数据由 app/db/persist.py 写入时自动算好，不需要再跑这个脚本。

用法：python -m scripts.backfill_derived_fields [--batch-size 500]
"""

from __future__ import annotations

import argparse
import time

from app.core import value_tags as value_tags_lib
from app.core.job_derive import apply_derived
from app.db.connection import SessionLocal
from app.db.schema import ScrapedJob


def main(batch_size: int = 500) -> None:
    if not SessionLocal:
        print("数据库未配置")
        return
    db = SessionLocal()
    try:
        approved_tags = value_tags_lib.list_approved(db)
        manual_map = value_tags_lib.load_manual_map(db)
        total = db.query(ScrapedJob).count()
        print(f"共 {total} 条，approved value_tags {len(approved_tags)} 条")

        done = 0
        t0 = time.monotonic()
        last_id = 0
        while True:
            rows = (
                db.query(ScrapedJob)
                .filter(ScrapedJob.id > last_id)
                .order_by(ScrapedJob.id)
                .limit(batch_size)
                .all()
            )
            if not rows:
                break
            for row in rows:
                manual_ids = manual_map.get((row.channel, row.external_id), set())
                apply_derived(row, approved_tags=approved_tags, manual_ids=manual_ids)
            db.commit()
            last_id = rows[-1].id
            done += len(rows)
            print(f"{done}/{total} ({time.monotonic() - t0:.1f}s)")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()
    main(args.batch_size)
