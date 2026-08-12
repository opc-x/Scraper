"""
X 远程办公招聘账号挖掘 —— 发现候选账号 + 抓历史发帖，规则见 rules/x_remote_hiring_accounts.md。

只负责机械抓取，不做置信度判断（那一步交给人工/AI 阅读 candidates 输出的原始数据）。

用法：
    python scripts/mine_x_remote_hiring.py
输出：
    /tmp/x_mining_raw.json —— {screen_name: {tweets: [...], sample_search_hits: n}}
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.channels.x import XAdapter  # noqa: E402

SEARCH_QUERIES = [
    "remote job hiring",
    "hiring remote developer",
    "we're hiring remote",
    "remote job alert",
    "remote position open",
    "hiring remote engineer",
]

MAX_CANDIDATES = 20  # 先小批量验证跑得通，别一上来就 100+ 请求把号弄挂
TWEETS_PER_CANDIDATE = 20
OUT_PATH = "/tmp/x_mining_raw.json"


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
        time.sleep(2)

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

    a._page.quit()
    from app.infra import chrome
    chrome.persist_profile("x")

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n完成，{len(results)} 个账号的原始数据已写入 {OUT_PATH}")


if __name__ == "__main__":
    main()
