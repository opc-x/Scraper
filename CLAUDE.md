# Scraper

AI-native 多渠道数据挖掘服务 — 基于优质数据源做数据接入，挖掘里面的价值 · 配置驱动 · 插拔式渠道

## 技术栈

| 层 | 技术 |
|---|---|
| 框架 | FastAPI |
| 语言 | Python 3.11+ |
| 抓取引擎 | DrissionPage (API 包监听，持久化 Chromium profile) |
| DB | Turso (libSQL，独立 scraper 库，免费档 5GB) |
| ORM | SQLAlchemy 2.0（`sqlalchemy-libsql` dialect） |
| 登录态持久化 | Cloudflare R2（Chromium profile 回传/拉取，见 `app/infra/r2.py`） |
| 部署 | Azure Container Instances (ACI, Docker 镜像, 见 `docs/azure-aci-deploy.md`) |

## 本地 AI 挖掘环境（重要，别搞反架构）

**数据挖掘（抓取 + AI 打标签/打分/置信度评估）重度依赖本机 Mac 环境跑，不在 Azure 生产服务里跑。**

- 本机装了 Claude Code / Codex CLI 订阅，`rules/*.md` 定义的挖掘规则由本机 AI 环境执行（人工触发或本地脚本），结果写入 Turso 数据库
- 生产环境（Azure ACI 上跑的 FastAPI 服务）**只从数据库读结果展示 + 提供接口**，不在生产里发起 LLM 调用、不跑挖掘任务——生产环境没有本机的 CLI 订阅，装不出来，也不该装
- `app/infra/llm.py` 走的是 DeepSeek API（渠道数据抽取用，走 `llm_api_key` 配置，这个可以在生产跑），跟本机挖掘用的 Claude/Codex 订阅是两套独立体系，不要混

## 目录结构

```
Scraper/
├── app/
│   ├── main.py              # FastAPI 入口 + 前端页面
│   ├── index.html            # 渠道配置 / 数据 / 接口 三段式验收页面
│   ├── api/routes/
│   │   ├── search.py         # POST /api/search — 实时抓取，写入 scraped_jobs
│   │   ├── channels.py       # GET /api/channels — 渠道列表（按 board 分组）
│   │   ├── config.py         # 渠道配置增删改查
│   │   ├── save.py           # POST /api/save — 收藏精选职位
│   │   └── scraped.py        # GET/DELETE /api/scraped — 全量抓取结果增删查
│   ├── adapters/              # boss/telegram/discord 等渠道 adapter
│   │   ├── base.py           # BaseAdapter 抽象类
│   │   ├── boss.py           # BOSS直聘 adapter (DrissionPage 监听 API 包)
│   │   └── registry.py       # 渠道注册表
│   ├── channels/
│   │   └── x.py              # X (Twitter) adapter，走 infra/chrome.py 持久化登录
│   ├── core/
│   │   ├── config.py         # 环境变量配置
│   │   ├── channel_config.py # 渠道配置 schema + board 分组 + DB 读写（带缓存）
│   │   └── models.py         # Pydantic 数据模型
│   ├── infra/
│   │   ├── chrome.py         # 持久化 Chromium profile（headless/交互登录）
│   │   ├── r2.py              # Chromium profile 回传/拉取 Cloudflare R2
│   │   └── llm.py            # DeepSeek 抽取职位信息（telegram/discord/x 共用）
│   └── db/
│       ├── connection.py     # Turso 连接（回落 Postgres）
│       ├── schema.py         # SQLAlchemy 模型（含 scraped_jobs 全量表）
│       └── persist.py        # 抓取结果写入 scraped_jobs
├── rules/                    # 数据挖掘规则定义（.md，人工可读）
├── scripts/
│   └── x_login.py            # X 渠道交互式登录脚本，本机手动跑一次
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## API 接口

```
POST   /api/search          ← 实时抓取（keyword, city, channel），写入 scraped_jobs
GET    /api/channels        ← 已接入渠道列表（按 board 分组）
GET    /api/channels/schema ← 渠道配置 schema + board 定义
PUT    /api/channels/config ← 保存渠道配置
DELETE /api/channels/config/{channel} ← 重置渠道配置
GET    /api/scraped         ← 全量抓取结果（可按 channel 过滤）
DELETE /api/scraped/{id}    ← 删除一条抓取记录
POST   /api/save            ← 收藏精选职位
GET    /api/saved           ← 已收藏列表
GET    /health               ← 健康检查
```

## 渠道适配器

新增渠道：
1. 在 `app/adapters/`（或 `app/channels/`，两个目录同一套模式）新建文件，继承 `BaseAdapter`
2. 实现 `search()` 和 `close()` 方法
3. 在 `app/adapters/registry.py` 注册
4. 需要登录态的渠道优先走 `app/infra/chrome.py`（持久化 profile + R2 回传），不要每次手动粘贴 cookie

## 本地开发

```bash
cp .env.example .env
# 填入 TURSO_DATABASE_URL + TURSO_AUTH_TOKEN，需要登录态的渠道再配 R2_* 和渠道自己的 key

pip install -e ".[dev]"
python -m app.main       # http://localhost:8000
```

## Docker 部署

```bash
docker compose up -d     # http://localhost:8000
```

## 设计原则

- 每次 `/api/search` 全量写入 `scraped_jobs`（数据挖掘要有数据可挖），`saved_jobs` 单独存用户手动收藏的精选，两张表不是一回事
- 每个渠道一个 Adapter，配置驱动，插拔式
- DrissionPage 监听 API 包优先（最稳），需要登录态的渠道走 `infra/chrome.py` 持久化 profile
- 独立微服务，独立数据库，与调用方 Web 解耦
- 数据挖掘（AI 打标签/置信度评估）在本机 Mac 环境跑，生产服务只读库展示，见上面「本地 AI 挖掘环境」

## 消费方

数据处理（抓取 + 规则前置筛选 + AI 打标签 + 打分排序）全部封装在这个服务内部，调用方只拿处理好的结果，不碰抓取逻辑。

- **JobSniper Web** — `boss` 渠道，职位抓取
- **signore**（晨报）— 计划新增渠道（如 `x`），把浏览器登录态/Cookie 维护也放在这个常驻服务里，signore 部署在 Vercel（无状态、装不下内嵌浏览器），只通过 API 调这里拿数据，不自己抓

新增渠道跟 `app/adapters/boss.py` 同一套模式，接口和目录结构不用为新调用方另起一套。
