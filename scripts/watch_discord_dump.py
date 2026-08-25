"""盯 Discord dump 文件，有新批次就入库。无人值守用。"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

DUMP = Path("/tmp/discord_thread_dump.jsonl")
DEST = Path("/Users/cuijian/opc-x/Scraper/data/discord_jobs_full.jsonl")

def main() -> None:
    last = -1
    while True:
        size = DUMP.stat().st_size if DUMP.exists() else 0
        if size != last and size > 0:
            DEST.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(DUMP, DEST)
            from scripts.import_discord_dump import main as import_main
            import sys
            sys.argv = ["import_discord_dump"]
            try:
                import_main()
            except Exception as exc:  # noqa: BLE001
                print(f"import failed: {exc}", flush=True)
            last = size
        time.sleep(40)


if __name__ == "__main__":
    main()
