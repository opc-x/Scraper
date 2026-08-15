# 规则：X「招聘 Agent 工程师」账号挖掘

## 目标

从 X 上挖掘出一批**主要发布 AI/LLM Agent 工程师（AI Agent Engineer / Agent Developer）招聘信息**的账号，产出高置信度账号名单，服务 `docs/job-search-strategy.md` Phase 2 里 X 渠道的求职私域打法。

## 判定标准

一个账号判定为「招聘 Agent 工程师账号」，需要满足：

1. **主题相关**：历史发帖以招聘 AI/LLM Agent 相关技术岗位为主 —— 职位名含 "AI Agent Engineer"、"Agent Developer"、"LLM Engineer"、"AI Engineer（职责含 Agent/RAG/自动化工具开发）" 等，不是泛泛的"招程序员"
2. **非一次性**：有持续发帖历史，不是注册后发一条就沉寂的僵尸/广告号
3. **非纯广告号**：不是单纯售卖课程、招聘中介导流、刷单广告一类的垃圾账号

## 置信度评分

对每个候选账号，基于其**历史发帖内容**（非单条帖子）判断，输出 0-100 的置信度，衡量"这是一个招 Agent 工程师的账号"的把握有多大。

- **保留阈值：置信度 > 70**
- 综合下面几个信号打分，不是关键词硬匹配：
  - 历史发帖里 Agent/LLM 相关招聘内容占比
  - 岗位信息完整度（职位名/技能要求/remote 与否/薪资）
  - 账号简介（bio）是否自我定位为创始人/HR/猎头/招聘 bot
  - 优先标注团队规模信号（≤5人 / 早期阶段），对应 `job-search-strategy.md` 里"团队规模权重最高"的核心诉求，命中的账号 value_score 应更高

## 候选账号的发现方式

用 Agent 工程师招聘相关关键词多轮搜索 X："hiring AI agent engineer"、"AI agent developer wanted"、"hiring LLM engineer remote"、"looking for agent engineer"、"AI agent engineer remote" 等，从搜索命中的帖子提取发帖人，去重后作为候选池，再逐个拉取历史发帖评分。

## 产出

- 目标数量：**100 个**账号（置信度 > 70 之后排序取前 100，不够就有多少出多少，不能为了凑数降阈值）
- 存放位置：入库 `mined_accounts` 表，`channel=x`，`topic=agent_engineer_hiring`
- 每条记录字段：`handle`（screen_name）、`confidence`、`value_score`、`tags`、`rationale`、`profile_url`、`bio`

## 已知限制 / 风险

- 拉取大量账号的历史发帖是高频请求，对登录态存在触发 X 风控的风险，分批跑、批间加大间隔
- 打分由本机 AI 环境（Claude Code）人工触发执行，不经过 DeepSeek API（参考 [issue #1](https://github.com/opc-x/Scraper/issues/1) 与 CLAUDE.md「本地 AI 挖掘环境」约定）
