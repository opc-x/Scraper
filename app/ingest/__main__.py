"""python -m app.ingest [channel]

不传 channel 就打印契约。拉数据默认 lens_only 入库。
"""

from __future__ import annotations

import argparse
import json
import sys

from app.ingest.contract import run_module
from app.ingest.registry import CHANNELS, specs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.ingest")
    parser.add_argument("channel", nargs="?", help="渠道名；省略则列出契约")
    parser.add_argument("--dry-run", action="store_true", help="只拉不写库")
    parser.add_argument("--no-lens", action="store_true", help="入库不过个人口径")
    parser.add_argument("--pages", type=int)
    parser.add_argument("--keyword", default="")
    parser.add_argument("--city", default="")
    parser.add_argument("--days", type=int)
    parser.add_argument("--months", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--path", default="")
    parser.add_argument("--channels", default="", help="telegram 只跑这些频道，逗号分隔")
    parser.add_argument("--min-confidence", type=int)
    args = parser.parse_args(argv)

    if not args.channel:
        rows = [
            {
                "channel": spec.channel,
                "lang": spec.lang,
                "implemented": spec.implemented,
                "needs_login": spec.needs_login,
                "title": spec.title,
            }
            for spec in specs()
        ]
        payload = {"channels": rows, "youtube": "not_a_job_source"}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    mod = CHANNELS.get(args.channel)
    if not mod:
        print(f"unknown channel: {args.channel}", file=sys.stderr)
        print("known:", " ".join(CHANNELS), file=sys.stderr)
        return 2

    kwargs: dict = {}
    if args.pages is not None:
        kwargs["pages"] = args.pages
    if args.keyword:
        kwargs["keyword"] = args.keyword
    if args.city:
        kwargs["city"] = args.city
    if args.days is not None:
        kwargs["days"] = args.days
    if args.months is not None:
        kwargs["months"] = args.months
    if args.limit is not None:
        kwargs["limit"] = args.limit
    if args.path:
        kwargs["path"] = args.path
    if args.channels:
        kwargs["channels"] = args.channels
    if args.min_confidence is not None:
        kwargs["min_confidence"] = args.min_confidence

    result = run_module(
        mod,
        persist=not args.dry_run,
        lens_only=not args.no_lens,
        **kwargs,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
