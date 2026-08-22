"""回填 scraped_jobs.posted_at —— 各渠道的时间藏在 raw 的不同字段里，格式也不统一。"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from sqlalchemy import text

from app.db.connection import engine

# discord 的 JobsBot 把时间写在正文里：「— 5/4/26, 3:03 AM Monday, May 4, 2026 at 3:03 AM」
DC_DATE_RE = re.compile(r"—\s*(\d{1,2})/(\d{1,2})/(\d{2}),")


def parse_any(value: str) -> datetime | None:
    if not value:
        return None
    v = str(value).strip()
    try:  # ISO：telegram / hackernews / remoteok
        return datetime.fromisoformat(v.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
    except ValueError:
        pass
    try:  # RFC 2822：weworkremotely 的 RSS pubDate
        return parsedate_to_datetime(v).astimezone(timezone.utc).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def main() -> None:
    with engine.connect() as c:
        rows = c.execute(text(
            "SELECT id, channel, raw, description FROM scraped_jobs WHERE posted_at IS NULL"
        )).fetchall()
    print(f"待回填 {len(rows)} 条", flush=True)

    updates: list[tuple[int, datetime]] = []
    miss = 0
    for jid, channel, raw, desc in rows:
        try:
            r = json.loads(raw) if isinstance(raw, str) else (raw or {})
        except (json.JSONDecodeError, TypeError):
            r = {}
        dt = None
        for key in ("posted_at", "published", "date", "pubDate", "captured_at"):
            if r.get(key):
                dt = parse_any(r[key])
                if dt:
                    break
        if not dt and channel == "discord":
            m = DC_DATE_RE.search(desc or "")
            if m:
                mo, day, yr = (int(x) for x in m.groups())
                try:
                    dt = datetime(2000 + yr, mo, day)
                except ValueError:
                    dt = None
        if dt:
            updates.append((jid, dt))
        else:
            miss += 1

    # 逐条 UPDATE 走 Turso 是 6000 次远程往返，慢到不可用；
    # 合成 CASE WHEN 批量更新，一批一次往返。
    BATCH = 400
    for i in range(0, len(updates), BATCH):
        chunk = updates[i:i + BATCH]
        cases = " ".join(f"WHEN {jid} THEN '{dt:%Y-%m-%d %H:%M:%S}'" for jid, dt in chunk)
        ids = ",".join(str(jid) for jid, _ in chunk)
        with engine.begin() as c:
            c.execute(text(
                f"UPDATE scraped_jobs SET posted_at = CASE id {cases} END WHERE id IN ({ids})"
            ))
        print(f"  已回填 {min(i + BATCH, len(updates))}/{len(updates)}", flush=True)

    print(f"完成：回填 {len(updates)} 条，拿不到时间 {miss} 条", flush=True)


if __name__ == "__main__":
    main()
