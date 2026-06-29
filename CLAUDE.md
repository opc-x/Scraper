# Scraper

AI-native 多渠道职位抓取微服务 — 现用现抓 · 配置驱动 · 插拔式渠道

## 技术栈

| 层 | 技术 |
|---|---|
| 框架 | FastAPI |
| 语言 | Python 3.11+ |
| 抓取引擎 | DrissionPage (API 包监听) + browser-use (AI 兜底) |
| DB | Neon PostgreSQL (独立 scraper 库) |
| ORM | SQLAlchemy 2.0 |
| 部署 | Azure VM (Docker) |

## 目录结构

```
Scraper/
├── app/
│   ├── main.py              # FastAPI 入口 + 前端页面
│   ├── index.html            # 狙击操作页面
│   ├── api/routes/
│   │   ├── search.py         # POST /api/search — 实时抓取
│   │   ├── channels.py       # GET /api/channels — 渠道列表
│   │   └── save.py           # POST /api/save — 收藏职位
│   ├── adapters/
│   │   ├── base.py           # BaseAdapter 抽象类
│   │   ├── boss.py           # BOSS直聘 adapter (DrissionPage 监听 API 包)
│   │   └── registry.py       # 渠道注册表
│   ├── core/
│   │   ├── config.py         # 环境变量配置
│   │   └── models.py         # Pydantic 数据模型
│   └── db/
│       ├── connection.py     # Neon 连接
│       └── schema.py         # SQLAlchemy 模型
├── Dockerfile
├── docker-compose.yml
└── pyproject.toml
```

## API 接口

```
POST /api/search     ← 实时抓取（keyword, city, channel, salary_min）
GET  /api/channels   ← 已接入渠道列表
POST /api/save       ← 收藏精选职位
GET  /api/saved      ← 已收藏列表
GET  /health         ← 健康检查
```

## 渠道适配器

新增渠道：
1. 在 `app/adapters/` 新建文件，继承 `BaseAdapter`
2. 实现 `search()` 和 `close()` 方法
3. 在 `registry.py` 注册

## 本地开发

```bash
cp .env.example .env
# 填入 DATABASE_URL + OPENAI_API_KEY

pip install -e ".[dev]"
python -m app.main       # http://localhost:8000
```

## Docker 部署

```bash
docker compose up -d     # http://localhost:8000
```

## 设计原则

- 现用现抓，不批量存储，只收藏精选
- 每个渠道一个 Adapter，配置驱动，插拔式
- DrissionPage 监听 API 包优先（最稳），browser-use AI 语义提取兜底
- 独立微服务，独立数据库，与 JobSniper Web 解耦
