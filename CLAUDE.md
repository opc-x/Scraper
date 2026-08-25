# Scraper

AI-native 多渠道数据挖掘服务 — 基于优质数据源做数据接入，挖掘里面的价值 · 配置驱动 · 插拔式渠道

**两个身份，别搞混**：① 给 JobSniper Web / signore 等下游 app 用的通用数据挖掘微服务（渠道抓取 + 落库 + API）；② `app/index.html` 本身也是账号本人（见 `docs/resumes/consolidated_2026.md`）在用的个人求职 app（收藏/归档/AI 画像/英语面试素材）。渠道 adapter、`scraped_jobs` 表这些是通用基础设施；`rules/remote_java_resume_match.md`、`scripts/score_jobs.py`、「实战」tab 这些是**这一个人**的个人化规则/功能，不是产品通用逻辑，改动前先分清楚改的是哪一层。

## 技术栈

| 层 | 技术 |
|---|---|
| 框架 | FastAPI |
| 语言 | Python 3.11+ |
| 抓取引擎 | DrissionPage (API 包监听，持久化 Chromium profile) |
| DB | Turso (libSQL，独立 scraper 库，免费档 5GB) |
| ORM | SQLAlchemy 2.0（`sqlalchemy-libsql` dialect） |
| 登录态持久化 | Cloudflare R2（Chromium profile 回传/拉取，见 `app/infra/r2.py`） |
| 部署 | 本机 Mac 常驻 + Cloudflare Tunnel（`scraper.opc-x.org`）。Azure ACI 已停用自动部署，`.github/workflows/deploy.yml` 改为手动触发（`workflow_dispatch`），避免每次 push 把 DNS 改回 Azure IP 跟本机隧道打架；历史踩坑记录见 `docs/azure-aci-deploy.md` |

## iOS PWA 视口与底栏（禁止回归）

- `frontend/index.html` 禁止加入 `viewport-fit=cover`，`apple-mobile-web-app-status-bar-style` 必须保持 `default`。
- 真机 standalone 模式下，`cover` + `black-translucent` 会缩短 WebView，但 `env(safe-area-inset-*)` 仍返回 `0`，结果是整个页面和 fixed 底栏上移，屏幕底部留下死区；这不是导航栏自身高度问题。
- 让 iOS 自己收缩视口，底栏保持 `bottom: 0`；不要用 `screen.height`、视口高度差或额外 padding 猜安全区。`env(safe-area-inset-bottom, 0px)` 只用于能正确上报 inset 的平台。
- 验证必须使用真机“添加到主屏幕”后的 PWA。完整事故记录和已验证实现见 `/Users/cuijian/opc-x/Ogden850App/CLAUDE.md` 的 “PWA viewport & safe area”。

## 本地 AI 挖掘环境（重要，别搞反架构）

**数据挖掘（抓取 + AI 打标签/打分/置信度评估）重度依赖本机 Mac 环境跑。因为现在部署形态本身就是本机 Mac + Cloudflare Tunnel（不是 Azure 了），"生产"和"本机"是同一台机器，`app/api/routes/jobs.py`、`scripts/score_jobs.py` 这类直接 `subprocess` 调 `claude` CLI 的代码能正常跑，不是架构违规。**

- 本机装了 Claude Code / Codex CLI 订阅，`rules/*.md` 定义的挖掘规则由本机 AI 环境执行（人工触发或本地脚本/API 路由），结果写入 Turso 数据库
- `app/infra/llm.py` 走的是 DeepSeek API（渠道数据抽取用，走 `llm_api_key` 配置，量大、便宜，走 API 不烧 Claude 订阅），跟本机挖掘用的 Claude/Codex 订阅是两套独立体系，按场景选：批量抽取结构化字段用 DeepSeek，需要读长文本（简历、规则文档）做综合判断的用本机 `claude` CLI
- 如果哪天真的换回纯 Azure 生产环境（跟本机分离），`app/api/routes/jobs.py` 里 `_run_claude()` 和 `scripts/score_jobs.py` 这类调用会失效，需要重新设计（比如画像生成只能本机批跑，生产只读结果）

## 目录结构

```
Scraper/
├── app/
│   ├── main.py              # FastAPI 入口 + 前端页面
│   ├── index.html            # 个人求职 app：首页 / 数据(职位库) / 我的(收藏归档) / 实战(英语面试素材) 四段式
│   ├── api/routes/
│   │   ├── search.py         # POST /api/search — 实时抓取，写入 scraped_jobs
│   │   ├── channels.py       # GET /api/channels — 渠道列表（按 board 分组）
│   │   ├── config.py         # 渠道配置增删改查
│   │   ├── save.py           # POST /api/save — 收藏精选职位（旧版，跟 marks.py 的收藏语义重叠，待收敛）
│   │   ├── scraped.py        # GET/DELETE /api/scraped — 全量抓取结果增删查 + summary 按渠道统计
│   │   ├── jobs.py           # GET /api/jobs/{id} 详情、POST /api/jobs/{id}/profile 本机 Claude 生成职位画像、/salary-stats 薪资统计
│   │   ├── marks.py          # POST/GET/DELETE /api/marks — 收藏/归档/已读，走 job_marks 表
│   │   ├── accounts.py       # GET/DELETE /api/accounts — mined_accounts（AI 挖到的账号 + 标签 + 置信度）
│   │   ├── drill.py          # GET /api/drill/search — 英语面试素材实时搜索，代理 YouTube Data API，个人化功能
│   │   ├── telegram_auth.py / telegram_ops.py  # Telegram 账号登录态管理 + 会话内搜索/拉取消息
│   ├── adapters/              # 渠道 adapter（职位类渠道，通用基础设施）
│   │   ├── base.py           # BaseAdapter 抽象类：search() + close()
│   │   ├── boss.py           # BOSS直聘 (DrissionPage 监听 API 包)
│   │   ├── discord.py        # Discord (User Token + 监听来源)
│   │   ├── telegram.py       # Telegram (Telethon)
│   │   ├── jobboards.py      # RemoteOK + WeWorkRemotely 二合一，公开数据源不用 key，channel 名 jobboards/remoteok/weworkremotely 都能查
│   │   ├── v2ex.py           # V2EX「酷工作」节点，公开 Atom feed，中英混杂社区招聘贴，只做机械关键词预筛
│   │   └── registry.py       # 渠道注册表，新渠道在这里 case 一下
│   ├── channels/              # 跟 adapters/ 同一套模式，历史原因分了个目录，新渠道两边都行
│   │   ├── x.py               # X (Twitter)，走 infra/chrome.py 持久化登录 + R2
│   │   └── youtube.py         # YouTube 官方 Data API，用 youtube_api_key，不需要浏览器登录态
│   ├── core/
│   │   ├── config.py         # 环境变量配置
│   │   ├── channel_config.py # 渠道配置 schema（CHANNEL_SCHEMA）+ board 分组 + DB 读写（带缓存）—— 注意：liepin/zhilian 在这里有 schema 配置入口，但 registry.py 里没有对应 adapter，配了也调不动，是个已知的未完成项
│   │   ├── salary.py          # 薪资文本解析 + 分桶
│   │   └── models.py         # Pydantic 数据模型
│   ├── infra/
│   │   ├── chrome.py         # 持久化 Chromium profile（headless/交互登录）
│   │   ├── r2.py              # Chromium profile 回传/拉取 Cloudflare R2
│   │   └── llm.py            # DeepSeek 抽取职位信息（telegram/discord/x 共用）
│   └── db/
│       ├── connection.py     # Turso 连接（回落 Postgres）
│       ├── schema.py         # SQLAlchemy 模型：scraped_jobs（含 match_score 字段）、job_profiles、job_marks、mined_accounts、x_accounts
│       └── persist.py        # 抓取结果写入 scraped_jobs / mined_accounts / x_accounts
├── rules/                    # 数据挖掘规则定义（.md，人工可读，本机 AI 执行）
│   ├── remote_java_resume_match.md      # 个人化规则：Java/Agent + 地点 + 外语环境，全渠道打分
│   ├── x_remote_hiring_accounts.md      # X 渠道远程招聘账号挖掘规则
│   └── x_agent_engineer_hiring_accounts.md
├── docs/
│   ├── program-entrypoints/             # 程序入口、渠道流水线、规则引擎和代码审查
│   ├── resumes/consolidated_2026.md     # 账号本人简历，job 画像 prompt 和 score_jobs.py 都读这份
│   └── interview_prep.md                # 「实战」tab 的精选视频清单 + 匹配度，本机 Claude 评的分
├── scripts/
│   ├── x_login.py            # X 渠道交互式登录脚本，本机手动跑一次
│   ├── mine_x_remote_hiring.py  # 按 rules/x_remote_hiring_accounts.md 抓候选账号历史发帖，只机械抓取
│   ├── sync_x_accounts.py    # 抓到的 X 账号 profile 写入 x_accounts 表
│   └── score_jobs.py         # 按 rules/remote_java_resume_match.md 批量给 scraped_jobs 打匹配度分，本机 claude CLI 跑
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## API 接口

```
POST   /api/search              ← 实时抓取（keyword, city, channel），写入 scraped_jobs
GET    /api/channels             ← 已接入渠道列表（按 board 分组）
GET    /api/channels/schema      ← 渠道配置 schema + board 定义
PUT    /api/channels/config      ← 保存渠道配置
DELETE /api/channels/config/{channel} ← 重置渠道配置
GET    /api/scraped              ← 全量抓取结果（可按 channel 过滤）
GET    /api/scraped/summary      ← 按渠道分组的数量统计
DELETE /api/scraped/{id}         ← 删除一条抓取记录
GET    /api/jobs/{id}            ← 职位详情 + 已生成的画像
POST   /api/jobs/{id}/profile    ← 本机 Claude CLI 生成/刷新职位画像（fit_score/verdict/建议），落库缓存
GET    /api/jobs/salary-stats    ← 薪资分布统计
POST   /api/marks                ← 收藏/归档/取消（job_marks 表）
GET    /api/marks                ← 按 state 查收藏/归档列表
GET    /api/marks/index          ← 收藏/归档/已读 id 索引，前端用来渲染状态
DELETE /api/marks/{id}           ← 取消收藏/归档
POST   /api/save                 ← 收藏精选职位（旧接口，跟 /api/marks 语义重叠，新功能优先用 marks）
GET    /api/saved                ← 已收藏列表（旧接口）
GET    /api/accounts             ← 挖掘出的账号列表（mined_accounts）
GET    /api/accounts/topics      ← 账号主题列表
DELETE /api/accounts/{id}        ← 删除一条挖到的账号
GET    /api/drill/search         ← 英语面试素材实时搜索，代理 YouTube Data API（个人化功能，不落库）
GET    /api/telegram/*           ← Telegram 账号登录态管理 + 会话内搜索/拉取消息/分类
GET    /health                    ← 健康检查
```

## 渠道适配器

新增渠道：
1. 在 `app/adapters/`（或 `app/channels/`，两个目录同一套模式）新建文件，继承 `BaseAdapter`
2. 实现 `search()` 和 `close()` 方法
3. 在 `app/adapters/registry.py` 注册（import + `match channel` 里加一个 case）
4. 如果这渠道要在渠道配置页可配置/可启停，还要在 `app/core/channel_config.py` 的 `CHANNEL_SCHEMA` 里加一条（不需要 key 的公开数据源渠道，`fields` 给空列表就行，参考 `v2ex`）
5. 需要登录态的渠道优先走 `app/infra/chrome.py`（持久化 profile + R2 回传），不要每次手动粘贴 cookie

已接入（registry.py 里有 case 的，才算真正能用）：
- `boss` — BOSS直聘，DrissionPage 监听 API 包
- `telegram` — Telethon
- `discord` — User Token + 监听来源
- `x` — `app/channels/x.py`，持久化登录 + R2
- `youtube` — `app/channels/youtube.py`，官方 Data API，`youtube_api_key`，不需要浏览器登录态
- `jobboards` / `remoteok` / `weworkremotely` — 公开 API/RSS，二合一，不需要 key
- `v2ex` — 「酷工作」节点公开 Atom feed，不需要 key，中英混杂社区招聘贴

**配了但没接（`CHANNEL_SCHEMA` 有 schema，`registry.py` 没有 case，点了会 `Unknown channel` 报错）**：`liepin`、`zhilian`。要接的话照 `boss.py` 的 DrissionPage 模式抄一份。

## 数据挖掘规则 / 打分脚本

程序入口、各渠道完整数据流程和规则复用边界统一见 `docs/program-entrypoints/README.md`。

`rules/*.md` 定义挖掘规则（人工可读），配套脚本在 `scripts/`：
- `scripts/x_login.py` — X 渠道交互式登录，本机手动跑一次，登录态经 `infra/r2.py` 回传
- `scripts/mine_x_remote_hiring.py` — 按 `rules/x_remote_hiring_accounts.md` 规则抓候选账号历史发帖，只做机械抓取不做置信度判断，输出到 `/tmp/x_mining_raw.json`
- `scripts/sync_x_accounts.py` — 把抓到的 X 账号 profile 写入 `x_accounts` 表（`python -m scripts.sync_x_accounts [handle ...]`，不传参则同步 `mined_accounts` 里 channel=x 的全部账号）
- `scripts/score_jobs.py` — **个人化**批量打分脚本，按 `rules/remote_java_resume_match.md` 规则（Java/Agent 方向 + 远程或杭州 + 明确外语环境，三项全要），读 `docs/resumes/consolidated_2026.md` 简历原文，调本机 `claude` CLI 给 `scraped_jobs` 每条打 `match_score`（0-100）+ 写 `job_profiles`。`python -m scripts.score_jobs [--days 90] [--refresh] [--channel x] [--limit N]`。这条规则的产出量级不设下限，凑数注水是反规则的行为，见规则文档结尾那段。

## 本地开发

```bash
cp .env.example .env
# 填入 TURSO_DATABASE_URL + TURSO_AUTH_TOKEN，需要登录态的渠道再配 R2_* 和渠道自己的 key

pip install -e ".[dev]"
python -m app.main       # http://localhost:8000
```

## 常用命令

```bash
pytest                              # 跑全部测试
pytest tests/x.py                   # 跑单个测试文件
pytest tests/x.py -k test_name      # 跑单个测试用例
ruff check .                        # lint
```

## Docker 部署

```bash
docker compose up -d     # http://localhost:8000
```

## 设计原则

- 每次 `/api/search` 全量写入 `scraped_jobs`（数据挖掘要有数据可挖），收藏/归档单独走 `job_marks` 表，两张表不是一回事
- 每个渠道一个 Adapter，配置驱动，插拔式；不需要登录态的公开数据源渠道（`jobboards`、`v2ex`）只做机械关键词预筛，不烧 LLM token，真正的语义判断（比如"是不是远程 Java 且匹配简历"）交给下游的批量打分脚本，别在 adapter 里塞语义判断逻辑
- DrissionPage 监听 API 包优先（最稳），需要登录态的渠道走 `infra/chrome.py` 持久化 profile
- 独立微服务，独立数据库，与调用方 Web 解耦
- 数据挖掘（AI 打标签/置信度评估/职位画像）在本机 Mac 环境跑（见上面「本地 AI 挖掘环境」）；DeepSeek 抽取（`app/infra/llm.py`）走 API，走哪不看"是不是生产"，看"是批量结构化抽取还是要综合判断"
- 通用基础设施（adapter、`scraped_jobs`、渠道配置）跟个人化功能（`remote_java_resume_match.md`、`score_jobs.py`、「实战」tab、`docs/interview_prep.md`）分层清楚，改个人化的东西不要动到通用基础设施的接口约定

## 消费方

数据处理（抓取 + 规则前置筛选 + AI 打标签 + 打分排序）全部封装在这个服务内部，调用方只拿处理好的结果，不碰抓取逻辑。

- **账号本人**（`app/index.html` 本身）— 个人求职 app，四个 tab：首页（总览+渠道配置入口）、数据（职位库，按渠道/技术标签筛选）、我的（收藏/归档/薪资统计）、实战（英语面试素材，`docs/interview_prep.md` 精选 + `/api/drill/search` 实时搜索）
- **JobSniper Web** — `boss` 渠道，职位抓取
- **signore**（晨报）— 计划新增渠道（如 `x`），把浏览器登录态/Cookie 维护也放在这个常驻服务里，signore 部署在 Vercel（无状态、装不下内嵌浏览器），只通过 API 调这里拿数据，不自己抓

新增渠道跟 `app/adapters/boss.py` 同一套模式，接口和目录结构不用为新调用方另起一套。
