# Handoff — BOSS 直聘续挖（2026-08-22 18:52）

给下一个 agent：先读这篇再动手。**不要一上来狂打接口。**

## 用户要什么

从 BOSS 直聘捞职位，口径：

1. Java
2. 远程 / 远程办公
3. Agent coding / 智能体
4. 跟简历 `docs/resumes/consolidated_2026.md` 比较匹配

数量：下限 150，上限不封顶。

另外点过顶栏三个入口，都要搞：

- 职位 → `https://www.zhipin.com/web/geek/jobs`
- 海归（用户写成「海龟」）→ `https://www.zhipin.com/returnee_jobs/`
- 海外 → `https://www.zhipin.com/overseas/`

侧栏浏览器用户会自己过滑块/安全验证，过完你再继续。

## 现在到底有多少

| 口径 | 数量 | 说明 |
|---|---:|---|
| `scraped_jobs` 里 `channel='boss'` | **164** | 真实入库总量（含更早一轮 + 本轮 upsert） |
| 本轮 httpx 筛后 `kept` | **77** | Java + 杭州，接口翻到第 4 页 |
| 本轮去重抓取 | **120** | 第 5 页 code 37 停 |
| `data/boss_jobs.json` | 最后一次 dump 的 77 条 | 会被脚本覆盖，别当全库 |
| `match_score` | **0** | 这 164 条还没跑 `scripts/score_jobs.py` |

**没搞到的：** 海归 tab、海外 tab、职位 tab 第 5 页及以后。

不是「渠道没接上」。`BossAdapter` 早就有。卡的是风控。

## 为啥总停 / 为啥右边浏览器没动静

两套浏览器，别混：

1. **Cursor 侧栏**（用户截图那扇）— profile 在  
   `~/Library/Application Support/Cursor/Partitions/cursor-browser/`  
   Cookie 明文在 SQLite `Cookies` 表（`wt2` / `zp_at` / `bst`）。用户在这里登录、过验证。
2. **DrissionPage** — `~/.scraper/chrome_profiles/boss`  
   另开一扇 Chrome，侧栏过了验证不等于这扇过了。

最近一轮 **164/77 不是点侧栏 DOM 翻出来的**，是读侧栏 Cookie，`httpx` 直连：

`GET https://www.zhipin.com/wapi/zpgeek/search/joblist.json`

`trust_env=False`（本机 `127.0.0.1:7897` 代理会 SSL 失败）。

第 5 页返回 **code 37「您的环境存在异常」**，脚本按设计停手。再打会变成 36 账户异常，然后 `verify.html`。

在侧栏里 `browser_navigate` 换 query/city 也会直接进验证页。点顶栏 link 比改 URL 稍好，**不能绕过风控**。

Chrome 地址栏 `page=N` **不会换数据**；httpx 的 `page` + `pageSize=30` 才会真分页。

## 代码入口

- 挖：`python -m scripts.mine_boss_jobs --httpx --min-jobs 150 --pages 6 --sleep 5`
- 适配器：`app/adapters/boss.py`（`/web/geek/jobs`，风控要等人点验证）
- 筛选：`scripts/mine_boss_jobs.py` 里 `keep_job`（Java/Agent + 远程/杭州/海外）
- 简历：`docs/resumes/consolidated_2026.md`，打分规则 `rules/remote_java_resume_match.md`
- 落库：`app/db/persist.py` → 本地 `data/scraper.db`（`local_sqlite_path`）

必须 `.venv` / `uv run`。环境变量代理要清空再打 zhipin。

## 下一个 agent 建议顺序

1. 看侧栏是不是列表页，不是 `verify.html`。是验证就让用户点，**不要自己连打 37**。
2. Cookie 从 Cursor `Cookies` 库重读（过验证后 `wt2`/`__zp_stoken__` 会变）。
3. httpx 继续：职位 Java 杭州从 page 5；再 `Java 远程` 全国；海归/海外用关键词 `Java 海归` / `Java 驻外` / `海外 Java`（那两个站未必走同一个 joblist，先抓包再写）。
4. `pageSize` 15–30，页间隔 ≥5s，**一出现 35/36/37 立刻 dump 再停**。
5. 满 150 或用户说停，再 `uv run python -m scripts.score_jobs --channel boss --engine claude`。
6. 不要开第二套 DrissionPage 去跟侧栏抢登录态。
7. `adapter.close()` 里 R2 回传遇到代理会 SSL 爆；已经 swallow 了，别再当成抓取失败。

## 用户配合方式

风控要人过：把验证页弹到侧栏，等人说「搞定了」再请求。不要锁着浏览器让人点不了滑块。
