"""Discord 招聘/技术社区服务器验活。

走 Discord 公开 invite 接口 GET /api/v10/invites/{code}?with_counts=true
（无需登录态、无需 bot），确认服务器真实存在并拿到人数。

用法：
    python -m scripts.verify_discord_servers --out data/discord_servers.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://discord.com/api/v10/invites/{code}?with_counts=true&with_expiration=true"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}

# (invite_code, 分类, 为什么值得进)
CANDIDATES: list[tuple[str, str, str]] = [
    # —— 通用大型编程社区，都有 #jobs / #hiring 频道
    ("python", "lang", "Python 官方社区，#jobs 频道常年有远程岗"),
    ("reactiflux", "lang", "React 生态最大社区，#job-board 质量高"),
    ("devcord", "general", "通用开发者社区，有 hiring 频道"),
    ("programming", "general", "综合编程社区"),
    ("theprogrammershangout", "general", "TPH，10w+ 开发者，#job-postings"),
    ("rust-lang-community", "lang", "Rust 社区"),
    ("golang", "lang", "Go 社区"),
    ("elixir-lang", "lang", "Elixir，远程友好公司密度高"),
    ("kotlinlang", "lang", "Kotlin 官方"),
    ("csharp", "lang", "C# 社区"),
    ("flutterdev", "lang", "Flutter"),
    ("laravel", "lang", "Laravel"),
    ("nestjs", "lang", "NestJS"),
    ("vuejs", "lang", "Vue"),
    ("nuxt", "lang", "Nuxt"),
    ("sveltesociety", "lang", "Svelte"),
    ("angular", "lang", "Angular"),
    ("astrodotbuild", "lang", "Astro"),
    ("htmx", "lang", "htmx"),
    ("deno", "lang", "Deno"),
    ("typescript", "lang", "TypeScript"),
    ("phoenix-framework", "lang", "Phoenix"),
    # —— 平台 / 基础设施厂商官方社区（招人 + 生态公司招人）
    ("supabase", "vendor", "Supabase 官方，生态公司常发远程岗"),
    ("vercel", "vendor", "Vercel 官方"),
    ("cloudflaredev", "vendor", "Cloudflare Developers"),
    ("railway", "vendor", "Railway"),
    ("planetscale", "vendor", "PlanetScale"),
    ("clickhouse", "vendor", "ClickHouse"),
    ("temporalio", "vendor", "Temporal"),
    ("grafana", "vendor", "Grafana"),
    ("hashicorp", "vendor", "HashiCorp"),
    ("tailwindcss", "vendor", "Tailwind"),
    # —— AI / Agent 方向（你现有 rules 的主战场）
    ("huggingface", "ai", "HuggingFace，AI 岗最集中"),
    ("langchain", "ai", "LangChain，agent 岗"),
    ("llamaindex", "ai", "LlamaIndex"),
    ("ollama", "ai", "Ollama"),
    ("cursor", "ai", "Cursor 编辑器社区"),
    ("crewai", "ai", "CrewAI multi-agent"),
    ("weaviate", "ai", "Weaviate 向量库"),
    ("qdrant", "ai", "Qdrant"),
    ("comfyorg", "ai", "ComfyUI"),
    ("eleutherai", "ai", "EleutherAI 研究社区"),
    ("openai", "ai", "OpenAI 官方社区"),
    ("replit", "ai", "Replit"),
    ("continuedev", "ai", "Continue"),
    ("openrouter", "ai", "OpenRouter"),
    ("modal-labs", "ai", "Modal"),
    # —— 直接以招聘 / 远程工作为主题
    ("remotejobs", "jobs", "远程岗聚合"),
    ("hire", "jobs", "Hire Talent & Find Jobs"),
    ("nextjob", "jobs", "NextJob 自由职业/远程"),
    ("remotway", "jobs", "Remotway 远程岗推送"),
    ("freelance", "jobs", "自由职业"),
    ("indiehackers", "jobs", "Indie Hackers"),
    ("wip", "jobs", "WIP 独立开发者"),
    ("techcareers", "jobs", "技术求职"),
    ("cscareers", "jobs", "CS Careers，面经 + 内推"),
    ("cscareerhub", "jobs", "CS Career Hub"),
    ("developersden", "general", "Developers Den"),
    ("codingden", "general", "Coding Den"),
    ("webdev", "general", "Web Dev"),
    ("dataengineering", "general", "数据工程"),
    ("devops", "general", "DevOps"),
    ("kubernetes", "general", "Kubernetes"),
]


def resolve(code: str) -> dict | None:
    try:
        req = urllib.request.Request(API.format(code=code), headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            time.sleep(5)
            return resolve(code)
        return None
    except Exception:  # noqa: BLE001
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/discord_servers.json")
    ap.add_argument("--min-members", type=int, default=0)
    args = ap.parse_args()

    rows, dead = [], []
    for code, kind, why in CANDIDATES:
        d = resolve(code)
        if not d or not d.get("guild"):
            dead.append(code)
            print(f"  ✗ {code}", file=sys.stderr)
            time.sleep(0.4)
            continue
        g = d["guild"]
        members = d.get("approximate_member_count") or 0
        if members < args.min_members:
            time.sleep(0.4)
            continue
        rows.append(
            {
                "channel": "discord",
                "category": kind,
                "note": why,
                "guild_id": g.get("id"),
                "name": g.get("name"),
                "description": (g.get("description") or "")[:300],
                "vanity_code": code,
                "invite_url": f"https://discord.gg/{code}",
                "members": members,
                "online": d.get("approximate_presence_count"),
                "verified": bool(g.get("verified")),
                "partnered": bool(g.get("partnered")),
            }
        )
        print(f"  ✓ {g.get('name')} ({members:,})", file=sys.stderr)
        time.sleep(0.4)

    rows.sort(key=lambda r: r["members"], reverse=True)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[discord] 存活 {len(rows)} / 候选 {len(CANDIDATES)} -> {out}", file=sys.stderr)
    print(f"[discord] 失效码: {', '.join(dead)}", file=sys.stderr)


if __name__ == "__main__":
    main()
