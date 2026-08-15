"""
X「招聘 Agent 工程师」账号挖掘 —— 发现候选账号 + 抓历史发帖，规则见 rules/x_agent_engineer_hiring_accounts.md。

只负责机械抓取，不做置信度判断（那一步交给本机 AI 环境阅读 candidates 输出的原始数据）。

用法：
    python scripts/mine_x_agent_engineer_hiring.py
输出：
    /tmp/x_agent_engineer_mining_raw.json —— {screen_name: {hits, tweets: [...]}}
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.channels.x import XAdapter  # noqa: E402

SEARCH_QUERIES = [
    "hiring AI agent engineer",
    "AI agent developer wanted",
    "hiring LLM engineer remote",
    "looking for agent engineer",
    "AI agent engineer remote",
    "hiring agent developer",
    "we're hiring AI agent",
    "seeking AI agent engineer",
]

MAX_CANDIDATES = 150
TWEETS_PER_CANDIDATE = 20
OUT_PATH = "/tmp/x_agent_engineer_mining_raw.json"


def main():
    a = XAdapter()
    candidates = {}  # screen_name -> {"hits": n}

    print("=== 阶段 1：发现候选账号 ===")
    for q in SEARCH_QUERIES:
        try:
            posts = a._search_posts_sync(q)
        except Exception as e:
            print(f"搜索 '{q}' 失败: {e}")
            continue
        found = 0
        for p in posts:
            sn = p.get("screen_name")
            if not sn:
                continue
            if sn not in candidates:
                candidates[sn] = {"hits": 0}
            candidates[sn]["hits"] += 1
            found += 1
        print(f"'{q}' -> {len(posts)} 条帖子，候选池累计 {len(candidates)} 个账号")
        time.sleep(3)

    screen_names = list(candidates.keys())[:MAX_CANDIDATES]
    print(f"\n候选账号共 {len(screen_names)} 个（封顶 {MAX_CANDIDATES}）")

    print("\n=== 阶段 2：抓每个账号的历史发帖 ===")
    results = {}
    for i, sn in enumerate(screen_names, 1):
        try:
            tweets = a.fetch_user_tweets_sync(sn)
        except Exception as e:
            print(f"[{i}/{len(screen_names)}] @{sn} 抓取失败: {e}")
            continue
        texts = [t["text"] for t in tweets if t.get("text")][:TWEETS_PER_CANDIDATE]
        results[sn] = {"hits": candidates[sn]["hits"], "tweets": texts}
        print(f"[{i}/{len(screen_names)}] @{sn}: {len(texts)} 条历史发帖")
        time.sleep(2)
        if i % 25 == 0:
            print("批间歇息 15s，降低风控触发概率...")
            time.sleep(15)

    if a._page:
        a._page.quit()
    from app.infra import chrome
    chrome.persist_profile("x")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n完成，{len(results)} 个账号的原始数据已写入 {OUT_PATH}")


if __name__ == "__main__":
    main()
