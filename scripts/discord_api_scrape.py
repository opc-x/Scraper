"""用 User Token 续扒 Discord 职位频道，写入 dump jsonl。不打印 token。

Token 来源（择一）：环境变量 DISCORD_USER_TOKEN，或 /tmp/discord_user_token。
Helper 已在 8766 时会同时 POST dump；否则直接追加 /tmp/discord_thread_dump.jsonl。
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

DUMP = Path("/tmp/discord_thread_dump.jsonl")
HEART = Path("/tmp/discord_scrape_heartbeat.json")
TOKEN_FILE = Path("/tmp/discord_user_token")
HOST = "http://127.0.0.1:8766"
API = "https://discord.com/api/v9"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "discord/0.0.309 Chrome/134.0.6998.205 Electron/35.3.0 Safari/537.36"
)

ALL_JOBS = {
    "guildId": "1488674851345531057",
    "guild": "CronJobs",
    "channelId": "1492516535497920624",
    "channel": "all-jobs",
    "kind": "forum",
}
EXTRA = [
    {"guildId": "851527874828566558", "guild": "Invide", "channelId": "896062986941251596", "channel": "remote-job-board", "kind": "text"},
    {"guildId": "880546729349488741", "guild": "Devs For Hire", "channelId": "1102927731353735279", "channel": "jobs-forum", "kind": "forum"},
    {"guildId": "880546729349488741", "guild": "Devs For Hire", "channelId": "927703276487606302", "channel": "paid-jobs", "kind": "text"},
    {"guildId": "969872191179071498", "guild": "Cookie", "channelId": "970486424002519150", "channel": "jobs", "kind": "text"},
    {"guildId": "969872191179071498", "guild": "Cookie", "channelId": "1529098285959217253", "channel": "job-opportunity", "kind": "text"},
    {"guildId": "1116994814349688875", "guild": "Job cord", "channelId": "1495948606644027564", "channel": "jobs", "kind": "text"},
    {"guildId": "1224897044259278858", "guild": "NextJob", "channelId": "1440140071847198853", "channel": "hiring", "kind": "forum"},
    {"guildId": "1224897044259278858", "guild": "NextJob", "channelId": "1464016709840142510", "channel": "hiring2", "kind": "forum"},
    {"guildId": "1224897044259278858", "guild": "NextJob", "channelId": "1459767557262282866", "channel": "find-jobs-here", "kind": "text"},
    {"guildId": "1297484076407853147", "guild": "FreeLanceBase", "channelId": "1297574700653740202", "channel": "jobs", "kind": "text"},
    {"guildId": "1297484076407853147", "guild": "FreeLanceBase", "channelId": "1297574818568339496", "channel": "post-job", "kind": "text"},
    {"guildId": "698366411864670250", "guild": "cscareers.dev", "channelId": "1306817435227394070", "channel": "intern_postings", "kind": "text"},
    {"guildId": "1002522561613135892", "guild": "Freelance Marketplace", "channelId": "1052528790707904573", "channel": "reddit-dev-jobs", "kind": "text"},
]


def _token() -> str:
    env = (os.environ.get("DISCORD_USER_TOKEN") or "").strip()
    if env:
        return env
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    raise SystemExit("missing Discord token: set DISCORD_USER_TOKEN or /tmp/discord_user_token")


def _dump_offset() -> int:
    ids: set[str] = set()
    if not DUMP.exists():
        return 0
    for line in DUMP.read_text().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict) or row.get("type") != "jobs":
            continue
        for item in row.get("batch") or []:
            tid = str((item or {}).get("threadId") or "")
            if tid:
                ids.add(tid)
    return len(ids)


def _heartbeat(state: dict) -> None:
    HEART.write_text(json.dumps(state), encoding="utf-8")
    try:
        _post(HOST + "/heartbeat", state)
    except Exception:  # noqa: BLE001
        pass


def _post(url: str, payload: dict) -> None:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as res:
        res.read()


def _write_batch(batch: list[dict]) -> None:
    payload = {"type": "jobs", "batch": batch}
    try:
        _post(HOST + "/dump", payload)
        return
    except Exception:  # noqa: BLE001
        pass
    DUMP.parent.mkdir(parents=True, exist_ok=True)
    with DUMP.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _urls_from(fm: dict) -> list[str]:
    out: list[str] = []
    for e in fm.get("embeds") or []:
        if e.get("url"):
            out.append(e["url"])
    for row in fm.get("components") or []:
        for c in row.get("components") or []:
            if c.get("url"):
                out.append(c["url"])
    import re
    out.extend(re.findall(r"https?://[^\s<>)]+", str(fm.get("content") or "")))
    seen: set[str] = set()
    uniq = []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq[:8]


def _api(token: str, path: str) -> tuple[int, dict | list | None]:
    req = urllib.request.Request(
        API + path,
        headers={"Authorization": token, "User-Agent": UA},
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as res:
            return res.status, json.loads(res.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {}
        return e.code, parsed


def _sleep_429(payload: dict | list | None) -> None:
    retry = 1.0
    if isinstance(payload, dict):
        retry = float(payload.get("retry_after") or 1)
    time.sleep(retry + 0.4)


def scrape_forum(token: str, src: dict, start_offset: int) -> None:
    offset = start_offset
    while True:
        path = (
            f"/channels/{src['channelId']}/threads/search"
            f"?sort_by=creation_time&sort_order=desc&limit=25&offset={offset}&archived=true"
        )
        status, data = _api(token, path)
        if status == 429:
            _sleep_429(data)
            continue
        if status != 200 or not isinstance(data, dict):
            _heartbeat({"phase": src["channel"], "offset": offset, "lastStatus": status})
            break
        threads = data.get("threads") or []
        fm_by_id = {fm.get("id"): fm for fm in (data.get("first_messages") or []) if isinstance(fm, dict)}
        batch = []
        for t in threads:
            fm = fm_by_id.get(t.get("id")) or {}
            meta = t.get("thread_metadata") or {}
            batch.append({
                "guildId": src["guildId"],
                "guild": src["guild"],
                "channelId": src["channelId"],
                "channel": src["channel"],
                "threadId": t.get("id"),
                "name": t.get("name") or "",
                "content": str(fm.get("content") or "")[:4000],
                "apply": _urls_from(fm),
                "ts": meta.get("create_timestamp") or fm.get("timestamp") or "",
            })
        if batch:
            _write_batch(batch)
        if not threads or data.get("has_more") is False:
            break
        offset += len(threads)
        _heartbeat({"phase": src["channel"], "offset": offset, "lastStatus": status})
        time.sleep(0.16)


def scrape_text(token: str, src: dict) -> None:
    before = ""
    cutoff = time.time() - 90 * 24 * 3600
    page = 0
    while page < 40:
        path = f"/channels/{src['channelId']}/messages?limit=100"
        if before:
            path += f"&before={before}"
        status, msgs = _api(token, path)
        if status == 429:
            _sleep_429(msgs)
            continue
        if status != 200 or not isinstance(msgs, list) or not msgs:
            break
        batch = []
        old = False
        for msg in msgs:
            ts = msg.get("timestamp") or ""
            try:
                epoch = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() if ts else 0
            except ValueError:
                epoch = 0
            if epoch and epoch < cutoff:
                old = True
            text = str(msg.get("content") or "")
            if len(text) < 20:
                continue
            batch.append({
                "guildId": src["guildId"],
                "guild": src["guild"],
                "channelId": src["channelId"],
                "channel": src["channel"],
                "threadId": msg.get("id"),
                "name": text.split("\n")[0][:180],
                "content": text[:4000],
                "apply": _urls_from(msg),
                "ts": ts,
            })
        if batch:
            _write_batch(batch)
        before = str(msgs[-1].get("id") or "")
        _heartbeat({"phase": src["channel"], "page": page, "lastStatus": status})
        if old or len(msgs) < 100 or not before:
            break
        page += 1
        time.sleep(0.18)


def main() -> None:
    token = _token()
    start = _dump_offset()
    _heartbeat({"phase": "all-jobs", "offset": start})
    scrape_forum(token, ALL_JOBS, start)
    for src in EXTRA:
        _heartbeat({"phase": f"{src['guild']}/{src['channel']}"})
        if src["kind"] == "forum":
            scrape_forum(token, src, 0)
        else:
            scrape_text(token, src)
    _heartbeat({"phase": "done"})


if __name__ == "__main__":
    main()
