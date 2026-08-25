"""把 Turso 里的全量数据一次性搬到本机 SQLite 文件，供切主存储用。

跟 app/db/connection.py 的正常路径分开：这里显式各自建一个 Turso 引擎和一个目标
SQLite 引擎，不看 settings.local_sqlite_path（那个是切换后 app 自己读的开关）。

用法：
    python -m scripts.migrate_to_sqlite [--out data/scraper.db]
"""
from __future__ import annotations

import argparse
import os

from sqlalchemy import create_engine, insert, select
from sqlalchemy.pool import QueuePool

from app.core.config import settings
from app.db.schema import Base


def _turso_engine():
    if not settings.turso_database_url:
        raise SystemExit("TURSO_DATABASE_URL 没配置，没有源数据可搬")
    host = settings.turso_database_url.replace("libsql://", "", 1)
    url = f"sqlite+libsql://{host}?secure=true"
    return create_engine(
        url,
        connect_args={"auth_token": settings.turso_auth_token},
        poolclass=QueuePool, pool_size=1, max_overflow=0, pool_timeout=60,
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/scraper.db")
    args = ap.parse_args()

    if os.path.exists(args.out):
        raise SystemExit(f"{args.out} 已存在，先确认要不要覆盖，手动删掉再跑")

    src = _turso_engine()
    dst = create_engine(f"sqlite:///{args.out}")
    Base.metadata.create_all(dst)

    with src.connect() as sc, dst.begin() as dc:
        for table in Base.metadata.sorted_tables:
            rows = sc.execute(select(table)).mappings().all()
            if not rows:
                print(f"{table.name}: 0 条，跳过")
                continue
            payload = [dict(r) for r in rows]
            for start in range(0, len(payload), 500):
                dc.execute(insert(table), payload[start:start + 500])
            print(f"{table.name}: 搬了 {len(payload)} 条")

    print("完成，校验行数：")
    with dst.connect() as dc:
        for table in Base.metadata.sorted_tables:
            count = dc.execute(select(table)).mappings().all()
            print(f"  {table.name}: {len(count)}")


if __name__ == "__main__":
    main()
