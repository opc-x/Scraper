"""入库门槛 AI 复议 —— 只捞回 Java 已命中、但其余条件（远程/居家/低英语/90天内/大陆可投）
加权比例没到阈值而被 filtered_out 的职位，不是全量跑 AI（怕滥用 token，也没必要给已经
过关或者压根不是 Java 岗的职位再问一遍模型）。

规则命中比例（ratio_pct）跟 AI 复议分（0-100）按 ingest_gate_config 里 rule_weight_pct/
ai_weight_pct 混合成最终分，跟 threshold_pct 比较，够了就把 filtered_out 翻回 False。
不管捞没捞回来都写 ai_gate_score，避免同一条job反复重跑；java 没命中的直接跳过并标 -2，
不占 AI 调用配额。

不改 job_derive.py / persist.py 的同步落库路径，纯事后批量脚本，模式抄 scripts/score_jobs.py。
"""
from __future__ import annotations

import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

from sqlalchemy import text

from app.core import job_rules
from app.core.job_derive import evaluate_ingest_gate
from app.db.connection import engine
from app.infra.local_ai import LocalAiError, run_sync

AI_SKIPPED_NOT_JAVA = -2

PROMPT = """你是招聘信息的语义复核员。规则引擎已经用关键词判断过这些职位是否符合
「远程或居家办公」「对英语没有硬性高门槛」「90 天内发布」「中国大陆可投」这几条，
但关键词会漏判——比如职位没写"remote"，但描述里说"分布式团队，全球任何地方都能工作"，
这种语义上符合、但关键词没命中的情况才是你要抓的。

职位已经确认是 Java 相关岗位，不用你再判断技术栈。
给每个职位打 0-100 分：分数代表"这条职位整体上有多大概率其实是符合远程/居家 + 低英语门槛
的，即使关键词没完全命中"。规则已经给的命中比例会附在每条职位里供你参考，不要盲目跟随，
你的价值就是发现规则错杀的。

只输出 JSON：{{"scores":[{{"id":1,"score":72,"reason":"一句话理由"}}]}}。
必须覆盖输入中的每个 id，reason 控制在 20 字以内，不要输出其它内容。

职位列表：
{jobs}
"""


def _chunks(rows: list, size: int) -> list:
    return [rows[i:i + size] for i in range(0, len(rows), size)]


def _skills(value) -> list:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _eligible_rows(rows: list[dict]) -> tuple[list[dict], list[int]]:
    """按 java 信号拆成 (可复议, 直接标 -2 跳过的 id 列表)。"""
    eligible: list[dict] = []
    skipped_ids: list[int] = []
    for row in rows:
        passed, detail = evaluate_ingest_gate(
            title=row["title"] or "", description=row["description"] or "",
            city=row["city"] or "", is_remote=bool(row["is_remote"]),
            skills=_skills(row["skills"]), channel=row["channel"] or "",
            posted_at=row["posted_at"],
        )
        if passed:
            # 已经不再被拦（比如阈值/规则被人工调整过），没必要占 AI 配额，标 -2 跳过。
            skipped_ids.append(row["id"])
            continue
        signals = detail.get("signals") or {}
        if not signals.get("java"):
            skipped_ids.append(row["id"])
            continue
        eligible.append({**row, "ratio_pct": detail.get("ratio_pct", 0)})
    return eligible, skipped_ids


def _score_batch(rows: list[dict], engine_name: str, timeout: int) -> tuple[list[dict], dict | None]:
    jobs = [{
        "id": row["id"], "title": row["title"], "city": row["city"],
        "skills": _skills(row["skills"]), "rule_hit_pct": row["ratio_pct"],
        "description": (row["description"] or "")[:800],
    } for row in rows]
    prompt = PROMPT.format(jobs=json.dumps(jobs, ensure_ascii=False, default=str))
    try:
        return rows, run_sync(prompt, engine=engine_name, timeout=timeout)
    except LocalAiError as exc:
        print(f"[ai] {exc}", flush=True)
        return rows, None


def _parse_scores(rows: list[dict], data: dict | None) -> dict[int, tuple[int, str]]:
    valid_ids = {int(row["id"]) for row in rows}
    out: dict[int, tuple[int, str]] = {}
    for item in (data or {}).get("scores", []):
        try:
            jid = int(item["id"])
            score = max(0, min(100, int(item["score"])))
            reason = str(item.get("reason", ""))[:60]
        except (KeyError, TypeError, ValueError):
            continue
        if jid in valid_ids:
            out[jid] = (score, reason)
    return out


def _write_results(updates: list[tuple[int, int, str, bool]]) -> None:
    """updates: (id, ai_gate_score, ai_gate_reason, rescued)"""
    for chunk in _chunks(updates, 200):
        with engine.begin() as conn:
            for jid, score, reason, rescued in chunk:
                conn.execute(text(
                    "UPDATE scraped_jobs SET ai_gate_score=:score, ai_gate_reason=:reason"
                    + (", filtered_out=0" if rescued else "")
                    + " WHERE id=:id"
                ), {"score": score, "reason": reason, "id": jid})


def _write_skipped(ids: list[int], score: int) -> None:
    for chunk in _chunks(ids, 400):
        id_list = ",".join(str(i) for i in chunk)
        with engine.begin() as conn:
            conn.execute(text(f"UPDATE scraped_jobs SET ai_gate_score={score} WHERE id IN ({id_list})"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", type=int, default=20)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--engine", default="claude", choices=("claude", "codex"))
    ap.add_argument("--timeout", type=int, default=420)
    ap.add_argument("--days", type=int, default=0, help="0 表示不限制发布时间")
    ap.add_argument("--channel", default="")
    args = ap.parse_args()

    clauses = ["filtered_out = 1", "ai_gate_score = -1"]
    params: dict[str, object] = {}
    if args.days:
        clauses.append("COALESCE(posted_at, first_seen_at) >= :since")
        params["since"] = (datetime.utcnow() - timedelta(days=args.days)).strftime("%Y-%m-%d %H:%M:%S")
    if args.channel:
        clauses.append("channel = :channel")
        params["channel"] = args.channel
    limit = " LIMIT :limit" if args.limit else ""
    if args.limit:
        params["limit"] = args.limit
    with engine.connect() as conn:
        raw_rows = conn.execute(text(f"""
            SELECT id,channel,title,city,skills,description,is_remote,posted_at
            FROM scraped_jobs WHERE {' AND '.join(clauses)} ORDER BY id{limit}
        """), params).mappings().all()
    all_rows = [dict(row) for row in raw_rows]
    jobs, skipped_ids = _eligible_rows(all_rows)
    if skipped_ids:
        _write_skipped(skipped_ids, AI_SKIPPED_NOT_JAVA)
    print(f"候选 {len(all_rows)} 条，跳过（非 Java 岗/已不再被拦）{len(skipped_ids)} 条，"
          f"待 AI 复议 {len(jobs)} 条", flush=True)
    if not jobs:
        return

    rule_pct = job_rules.rule_by_key("ingest_gate_config", "rule_weight_pct")
    ai_pct = job_rules.rule_by_key("ingest_gate_config", "ai_weight_pct")
    threshold_row = job_rules.rule_by_key("ingest_gate_config", "threshold_pct")
    rule_weight = rule_pct.weight if rule_pct else 70
    ai_weight = ai_pct.weight if ai_pct else 30
    threshold_pct = threshold_row.weight if threshold_row else 80

    batches = _chunks(jobs, max(1, args.batch))
    print(f"共 {len(batches)} 批，规则权重 {rule_weight} / AI 权重 {ai_weight}，阈值 {threshold_pct}", flush=True)

    pending: list[tuple[int, int, str, bool]] = []
    done = rescued = failed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(_score_batch, batch, args.engine, args.timeout) for batch in batches]
        for future in as_completed(futures):
            batch, data = future.result()
            scores = _parse_scores(batch, data)
            if len(scores) != len(batch):
                failed += len(batch) - len(scores)
            for row in batch:
                if row["id"] not in scores:
                    continue
                ai_score, reason = scores[row["id"]]
                final_pct = round(row["ratio_pct"] * rule_weight / 100 + ai_score * ai_weight / 100)
                is_rescued = final_pct >= threshold_pct
                pending.append((row["id"], ai_score, reason, is_rescued))
                done += 1
                rescued += 1 if is_rescued else 0
            if len(pending) >= 200:
                _write_results(pending)
                pending.clear()
            print(f"已复议 {done}/{len(jobs)}，捞回 {rescued}，失败保留 {failed}", flush=True)
    if pending:
        _write_results(pending)
    print(f"完成：复议 {done}，捞回 {rescued}，失败保留 -1 的 {failed}", flush=True)


if __name__ == "__main__":
    main()
