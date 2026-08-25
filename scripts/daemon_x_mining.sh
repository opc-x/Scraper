#!/usr/bin/env bash
# X 招聘账号无人值守挖掘 —— 抓取 + AI 打标签，循环跑到手动停止。
#
#   bash scripts/daemon_x_mining.sh start   # 起（自带 caffeinate 防休眠）
#   bash scripts/daemon_x_mining.sh stop
#   bash scripts/daemon_x_mining.sh status
#
# 单实例锁是硬要求：两个进程抢同一个 Chromium profile 会让抓取全部返回空。

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

PY=".venv/bin/python"
export CHROME_PROFILE_ROOT="$HOME/.scraper/chrome_profiles"
LOCK="/tmp/scraper_x_daemon.lock"
LOG="data/daemon_x.log"
PIDFILE="/tmp/scraper_x_daemon.pid"

log() { echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

loop() {
  mkdir -p data
  local round=0 backoff=60
  while true; do
    round=$((round + 1))
    log "=== 第 $round 轮开始 ==="

    # 抓取：--resume 复用已抓到的，抓空的账号下轮自动重试
    before=$($PY -c "import json;print(len(json.load(open('data/x_mining_raw.json'))))" 2>/dev/null || echo 0)
    $PY -m scripts.mine_x_remote_hiring_bulk --target 0 --resume --pace 2.5 >>"$LOG" 2>&1
    after=$($PY -c "import json;print(len(json.load(open('data/x_mining_raw.json'))))" 2>/dev/null || echo 0)
    withtweets=$($PY -c "import json;d=json.load(open('data/x_mining_raw.json'));print(sum(1 for v in d.values() if v.get('tweets')))" 2>/dev/null || echo 0)
    log "抓取：候选池 $before -> $after，其中有发帖数据的 $withtweets"

    # 打标签：只打没打过的，跑到打完为止
    $PY -m scripts.tag_x_accounts >>"$LOG" 2>&1
    tagged=$($PY -c "import json;print(len(json.load(open('data/x_tagged_accounts.json'))))" 2>/dev/null || echo 0)
    log "打标签：累计 $tagged 个"

    # 刷新汇总文件，随时可验收
    $PY -m scripts.export_job_sources --out data/job_sources.md >>"$LOG" 2>&1

    # 这轮没抓到新账号 = 大概率被限流，退避加倍（封顶 30 分钟）
    if [ "$after" -le "$before" ]; then
      backoff=$(( backoff * 2 )); [ "$backoff" -gt 1800 ] && backoff=1800
      log "本轮无新增，退避 ${backoff}s"
    else
      backoff=60
    fi
    # Chromium 有时会留残骸，进下一轮前清干净
    pkill -f "scraper/chrome_profiles" 2>/dev/null
    sleep "$backoff"
  done
}

case "${1:-start}" in
  start)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "已经在跑了，pid $(cat "$PIDFILE")"; exit 1
    fi
    pkill -f mine_x_remote_hiring_bulk 2>/dev/null
    sleep 2
    # caffeinate -dimsu：合盖/闲置都不休眠，否则半夜断在那儿
    nohup caffeinate -dimsu bash "$0" _loop >>"$LOG" 2>&1 &
    echo $! > "$PIDFILE"
    echo "已启动，pid $(cat "$PIDFILE")，日志 $LOG"
    ;;
  _loop) echo $$ > "$PIDFILE"; loop ;;
  stop)
    [ -f "$PIDFILE" ] && kill "$(cat "$PIDFILE")" 2>/dev/null
    pkill -f mine_x_remote_hiring_bulk 2>/dev/null
    pkill -f "bash.*daemon_x_mining" 2>/dev/null
    rm -f "$PIDFILE"; echo "已停"
    ;;
  status)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
      echo "运行中，pid $(cat "$PIDFILE")"
    else
      echo "未运行"
    fi
    tail -12 "$LOG" 2>/dev/null
    ;;
  *) echo "用法: $0 {start|stop|status}"; exit 1 ;;
esac
