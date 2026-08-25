"""把各渠道挖到的求职信源汇总成一份文件。

用法：
    python -m scripts.export_job_sources --out data/job_sources.md
读取 data/ 下各渠道的 json，外加 DB 里已挖的 X 账号。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

DATA = Path("data")


def load(name: str) -> list[dict]:
    p = DATA / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []


def x_accounts() -> list[dict]:
    local = load("x_hiring_accounts.json")
    if local:
        return local
    try:
        from sqlalchemy import text

        from app.db.connection import engine

        if not engine:
            return []
        with engine.connect() as c:
            rows = c.execute(
                text(
                    "SELECT handle, profile_url, confidence, value_score, tags, bio "
                    "FROM mined_accounts WHERE channel = 'x' ORDER BY confidence DESC"
                )
            )
            return [
                {
                    "handle": r[0],
                    "url": r[1],
                    "confidence": r[2],
                    "value_score": r[3],
                    "tags": r[4],
                    "bio": (r[5] or "")[:160],
                }
                for r in rows
            ]
    except Exception:  # noqa: BLE001
        return []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/job_sources.md")
    args = ap.parse_args()

    hn = load("hn_hiring.json")
    dc = load("discord_servers.json")
    tg = load("telegram_job_channels.json")
    xs = x_accounts()

    lines: list[str] = ["# 海外远程岗位信源汇总", ""]
    lines.append(
        f"HN 岗位 {len(hn)} · Discord 服务器 {len(dc)} · Telegram 频道 {len(tg)} · X 账号 {len(xs)}"
    )
    lines += ["", "---", "", f"## Discord 服务器（{len(dc)}，已验活）", ""]
    lines.append("| 人数 | 服务器 | 邀请链接 | 为什么 |")
    lines.append("|---:|---|---|---|")
    for r in dc:
        lines.append(f"| {r['members']:,} | {r['name']} | {r['invite_url']} | {r['note']} |")

    lines += ["", f"## Telegram 频道（{len(tg)}，公开预览可直接读）", ""]
    lines.append("| 订阅 | 语言 | 频道 | 链接 | 命中关键词 |")
    lines.append("|---:|---|---|---|---|")
    for r in tg:
        lines.append(
            f"| {r['subscribers']:,} | {r.get('lang', '?')} | {r['title'][:40]} | "
            f"{r['url']} | {', '.join(r['job_keyword_hits'][:6])} |"
        )

    lines += ["", f"## Hacker News 远程岗位（{len(hn)}，近 6 期 who-is-hiring）", ""]
    lines.append("| 公司 | 岗位 | 技术栈 | 链接 |")
    lines.append("|---|---|---|---|")
    for r in hn:
        lines.append(
            f"| {r['company'][:40]} | {r['role'][:50]} | {', '.join(r['stack'][:5])} | {r['url']} |"
        )

    tg_x = load("x_tagged_accounts.json")
    tagged = [t for t in (tg_x.values() if isinstance(tg_x, dict) else []) if not t.get("spam")]
    if tagged:
        # 排序按「中国境内可投 > 价值分 > 置信度」，这才是你实际能投的顺序
        tagged.sort(
            key=lambda t: (
                bool(t.get("china_friendly")),
                t.get("value_score") or 0,
                t.get("confidence") or 0,
            ),
            reverse=True,
        )
        lines += ["", f"## X 招聘账号（{len(tagged)}，已 AI 打标签）", ""]
        lines.append(
            "| 账号 | 置信 | 价值 | 方向 | 远程 | 地域 | 中国可投 | 薪资 | 技术栈 | 文化氛围 |"
        )
        lines.append("|---|---:|---:|---|---|---|:-:|---|---|---|")
        for t in tagged:
            lines.append(
                f"| [@{t['handle']}]({t.get('profile_url', '')}) | {t.get('confidence')} "
                f"| {t.get('value_score')} | {', '.join(t.get('roles') or [])} "
                f"| {t.get('remote', '')} | {', '.join((t.get('regions') or [])[:3])} "
                f"| {'✓' if t.get('china_friendly') else '✗'} | {(t.get('salary') or '')[:24]} "
                f"| {', '.join((t.get('stack') or [])[:5])} | {(t.get('culture') or '')[:40]} |"
            )
    else:
        lines += ["", f"## X 招聘账号（{len(xs)}，来自本地结果或 mined_accounts）", ""]
        lines.append("| 账号 | 置信度 | 价值分 | bio |")
        lines.append("|---|---:|---:|---|")
        for r in xs:
            confidence = r.get("confidence", r.get("prescreen", 0))
            value_score = r.get("value_score", r.get("prescreen", 0))
            lines.append(f"| @{r['handle']} | {confidence} | {value_score} | {r['bio'][:80]} |")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"-> {out}  (hn={len(hn)} discord={len(dc)} telegram={len(tg)} x={len(xs)})")


if __name__ == "__main__":
    main()
