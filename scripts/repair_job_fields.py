"""回填 scraped_jobs 里能确定还原的关键字段。

能修：原文链接（按渠道从 id/raw 还原）、Discord 地点、salary_cny、
V2EX `v2ex_<tid>` 跟数字 tid 的重复行。

不能修：Discord 浏览器抓取时没记下消息 URL，jsonl 的 url 也是空的，
没有 channel/message id 就不能编 discord.com/channels/... 链接。

用法：
    python -m scripts.repair_job_fields --dry-run
    python -m scripts.repair_job_fields
"""

from __future__ import annotations

import argparse

from app.core import value_tags as value_tags_lib
from app.core.job_derive import apply_derived
from app.core.job_origin import city_from_discord_text, origin_url
from app.db.connection import SessionLocal
from app.db.schema import JobMark, JobProfile, JobQualityReport, JobValueTag, ScrapedJob

RELATED = (JobMark, JobProfile, JobQualityReport, JobValueTag)


def _retarget(db, *, channel: str, old_ext: str, new_ext: str, keep_id: int) -> None:
    for model in RELATED:
        rows = db.query(model).filter_by(channel=channel, external_id=old_ext).all()
        for row in rows:
            clash = (
                db.query(model)
                .filter_by(channel=channel, external_id=new_ext)
                .first()
            )
            if clash is not None and clash.id != row.id:
                db.delete(row)
                continue
            row.external_id = new_ext
            if hasattr(row, "scraped_job_id"):
                row.scraped_job_id = keep_id


def _merge_v2ex(db, dry_run: bool) -> dict[str, int]:
    stats = {"renamed": 0, "merged": 0, "deleted": 0}
    rows = db.query(ScrapedJob).filter_by(channel="v2ex").all()
    by_ext = {row.external_id: row for row in rows}
    prefixed = [row for row in rows if row.external_id.startswith("v2ex_")]
    for row in prefixed:
        tid = row.external_id.removeprefix("v2ex_")
        if not tid or tid == row.external_id:
            continue
        keep = by_ext.get(tid)
        if keep is None:
            stats["renamed"] += 1
            if dry_run:
                continue
            row.external_id = tid
            if not (row.url or "").strip():
                row.url = f"https://www.v2ex.com/t/{tid}"
            by_ext[tid] = row
            continue
        stats["merged"] += 1
        stats["deleted"] += 1
        if dry_run:
            continue
        if keep.company in ("", "未知") and row.company not in ("", "未知"):
            keep.company = row.company
        if not (keep.url or "").strip() and row.url:
            keep.url = row.url
        if len(row.description or "") > len(keep.description or ""):
            keep.description = row.description
        _retarget(db, channel="v2ex", old_ext=row.external_id, new_ext=tid, keep_id=keep.id)
        db.delete(row)
    return stats


def main(dry_run: bool = False) -> None:
    if not SessionLocal:
        print("数据库未配置")
        return
    db = SessionLocal()
    try:
        approved_tags = value_tags_lib.list_approved(db)
        manual_map = value_tags_lib.load_manual_map(db)
        rows = db.query(ScrapedJob).all()
        filled_url = filled_city = filled_cny = 0
        for row in rows:
            resolved = origin_url(
                row.channel, row.external_id, row.url or "",
                row.raw if isinstance(row.raw, dict) else {},
                row.description or "",
            )
            if resolved and resolved != (row.url or ""):
                filled_url += 1
                if not dry_run:
                    row.url = resolved
            if row.channel == "discord" and not (row.city or "").strip():
                city = city_from_discord_text(row.description or "")
                if city:
                    filled_city += 1
                    if not dry_run:
                        row.city = city
            before_cny = row.salary_cny or ""
            apply_derived(
                row,
                approved_tags=approved_tags,
                manual_ids=manual_map.get((row.channel, row.external_id), set()),
            )
            if (row.salary_cny or "") and (row.salary_cny or "") != before_cny:
                filled_cny += 1

        v2ex_stats = _merge_v2ex(db, dry_run)
        if dry_run:
            db.rollback()
        else:
            db.commit()
            from app.api.routes.scraped import invalidate_scraped_cache
            invalidate_scraped_cache()

        print(
            f"url+{filled_url} city+{filled_city} salary_cny+{filled_cny} "
            f"v2ex_renamed={v2ex_stats['renamed']} v2ex_merged={v2ex_stats['merged']} "
            f"v2ex_deleted={v2ex_stats['deleted']} dry_run={dry_run}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    main(parser.parse_args().dry_run)
