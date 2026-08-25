from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TelegramAccount(Base):
    __tablename__ = "telegram_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    api_id: Mapped[str] = mapped_column(String(32), nullable=False)
    api_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    session_str: Mapped[str] = mapped_column(Text, server_default="", default="")
    is_active: Mapped[bool] = mapped_column(server_default="true", default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ChannelConfig(Base):
    __tablename__ = "channel_configs"

    channel: Mapped[str] = mapped_column(String(32), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=False)
    config_data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class ChannelSyncRun(Base):
    """渠道手动同步任务；状态与报告持久化，关闭前端后仍可恢复。"""

    __tablename__ = "channel_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    keyword: Mapped[str] = mapped_column(String(128), default="")
    city: Mapped[str] = mapped_column(String(64), default="")
    query: Mapped[str] = mapped_column(Text, default="")
    parsed_query: Mapped[dict] = mapped_column(JSON, default=dict)
    pulled: Mapped[int] = mapped_column(Integer, default=0)
    coverage: Mapped[str] = mapped_column(String(256), default="")
    error: Mapped[str] = mapped_column(Text, default="")
    logs: Mapped[dict] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ChannelSyncPreset(Base):
    """高频抓取查询预设；只是召回参数，不是职位判断规则。"""

    __tablename__ = "channel_sync_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class SavedJob(Base):
    __tablename__ = "saved_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    company: Mapped[str] = mapped_column(String(256), nullable=False)
    salary: Mapped[str] = mapped_column(String(64), default="")
    city: Mapped[str] = mapped_column(String(64), default="")
    experience: Mapped[str] = mapped_column(String(64), default="")
    education: Mapped[str] = mapped_column(String(64), default="")
    skills: Mapped[dict] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(512), default="")
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[dict] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class JobMark(Base):
    """用户对某条抓取结果的标记：收藏或归档。一条职位同时只有一种状态。

    存快照而不是外键，是因为 scraped_jobs 会被重新导入/清理，
    用户收藏的东西不该跟着消失。
    """

    __tablename__ = "job_marks"
    __table_args__ = (UniqueConstraint("channel", "external_id", name="uq_job_mark"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(16), default="")  # saved | archived | ""（仅已读）
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 已阅读，跟收藏/归档独立
    scraped_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(256), default="")
    company: Mapped[str] = mapped_column(String(256), default="")
    salary: Mapped[str] = mapped_column(String(64), default="")
    city: Mapped[str] = mapped_column(String(64), default="")
    skills: Mapped[dict] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(512), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class JobProfile(Base):
    """本机 AI 生成的职位综合评估，按 scraped_job 缓存，生成一次反复看。"""

    __tablename__ = "job_profiles"
    __table_args__ = (UniqueConstraint("channel", "external_id", name="uq_job_profile"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    scraped_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verdict: Mapped[str] = mapped_column(String(32), default="")      # 强烈推荐 / 值得一投 / 谨慎 / 不建议
    fit_score: Mapped[int] = mapped_column(Integer, default=0)        # 0-100 匹配度
    salary_min: Mapped[int] = mapped_column(Integer, default=0)       # 年薪 USD，供统计用
    salary_max: Mapped[int] = mapped_column(Integer, default=0)
    profile: Mapped[dict] = mapped_column(JSON, default=dict)         # 画像全文
    model: Mapped[str] = mapped_column(String(64), default="")
    generated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ScrapedJob(Base):
    """每次 /api/search 抓到的全量结果，跟用户手动收藏的 SavedJob 分开存。"""

    __tablename__ = "scraped_jobs"
    __table_args__ = (UniqueConstraint("channel", "external_id", name="uq_scraped_job"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    company: Mapped[str] = mapped_column(String(256), nullable=False)
    salary: Mapped[str] = mapped_column(String(64), default="")
    salary_cny: Mapped[str] = mapped_column(String(64), default="")  # 人民币可读口径，给中国人看的
    city: Mapped[str] = mapped_column(String(64), default="")
    experience: Mapped[str] = mapped_column(String(64), default="")
    education: Mapped[str] = mapped_column(String(64), default="")
    skills: Mapped[dict] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(String(512), default="")
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)  # 岗位发布时间，来自各渠道原始数据
    match_score: Mapped[int] = mapped_column(Integer, default=-1)  # 跟简历的匹配度 0-100，-1 = 还没算
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # 以下是写时预计算的衍生字段（见 app/core/job_derive.py），列表/筛选接口只读这些列，
    # 不再对全量数据现场跑正则——避免读接口的响应时间随数据量线性变长。
    # value_score/value_tags 依赖用户可编辑的 value_tags 规则库，规则变更时批量重算一次
    # （见 app/api/routes/value_tags.py），不是每次读都算。
    core_tags: Mapped[dict] = mapped_column(JSON, default=list)
    regions: Mapped[dict] = mapped_column(JSON, default=list)
    is_remote: Mapped[bool] = mapped_column(Boolean, default=False)
    interest_tags: Mapped[dict] = mapped_column(JSON, default=list)
    preference_score: Mapped[int] = mapped_column(Integer, default=0)
    salary_min_usd: Mapped[int] = mapped_column(Integer, default=0)
    salary_max_usd: Mapped[int] = mapped_column(Integer, default=0)
    salary_bucket: Mapped[str] = mapped_column(String(32), default="")
    data_quality_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    value_score: Mapped[int] = mapped_column(Integer, default=50)
    value_tags: Mapped[dict] = mapped_column(JSON, default=list)
    derived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    filtered_out: Mapped[bool] = mapped_column(Boolean, default=False)  # 入库门槛未达标，见 job_derive.evaluate_ingest_gate
    ai_gate_score: Mapped[int] = mapped_column(Integer, default=-1)  # AI 对入库门槛的复核分 0-100，-1=还没跑，见 scripts/rescue_ingest_gate.py
    ai_gate_reason: Mapped[str] = mapped_column(String(160), default="")


class MinedAccount(Base):
    """账号挖掘结果：某渠道下抓到的账号 + AI 打的标签/置信度，跟帖子/职位（ScrapedJob）是两回事。"""

    __tablename__ = "mined_accounts"
    __table_args__ = (UniqueConstraint("channel", "topic", "handle", name="uq_mined_account"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    topic: Mapped[str] = mapped_column(String(64), nullable=False)  # 挖掘主题，比如 remote_hiring
    handle: Mapped[str] = mapped_column(String(128), nullable=False)  # screen_name / 频道名
    profile_url: Mapped[str] = mapped_column(String(512), default="")
    bio: Mapped[str] = mapped_column(Text, default="")  # 账号自己写的简介，原文
    confidence: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-100，是否符合主题
    value_score: Mapped[int] = mapped_column(Integer, default=0)  # 0-100，内容对我的价值
    kept: Mapped[bool] = mapped_column(Boolean, default=True)  # 是否过了阈值
    tags: Mapped[dict] = mapped_column(JSON, default=list)
    rationale: Mapped[str] = mapped_column(Text, default="")
    scored_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class XAccount(Base):
    """X 账号原始档案：账号本身的公开资料快照（粉丝数/简介/头像等），跟主题无关，
    是所有挖掘/分析动作的底表——不管做哪个 topic 的判断，都从这张表里取账号基础信息，
    不用每次重新抓。跟 MinedAccount（某个 topic 下 AI 打的标签/置信度）是两张不同的表。
    """

    __tablename__ = "x_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rest_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # X 内部用户 id，稳定不变
    screen_name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)  # @handle，可能会改
    name: Mapped[str] = mapped_column(String(256), default="")  # 昵称
    bio: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(String(256), default="")
    website_url: Mapped[str] = mapped_column(String(512), default="")
    avatar_url: Mapped[str] = mapped_column(String(512), default="")
    banner_url: Mapped[str] = mapped_column(String(512), default="")
    x_created_at: Mapped[str] = mapped_column(String(64), default="")  # 账号在 X 上的注册时间原文
    followers_count: Mapped[int] = mapped_column(Integer, default=0)
    following_count: Mapped[int] = mapped_column(Integer, default=0)
    tweets_count: Mapped[int] = mapped_column(Integer, default=0)
    media_tweets_count: Mapped[int] = mapped_column(Integer, default=0)
    favorites_count: Mapped[int] = mapped_column(Integer, default=0)  # 账号点赞过的数量
    is_blue_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)  # 旧版官方认证（跟 blue 认证是两回事）
    protected: Mapped[bool] = mapped_column(Boolean, default=False)
    pinned_tweet_ids: Mapped[dict] = mapped_column(JSON, default=list)
    raw: Mapped[dict] = mapped_column(JSON, default=dict)  # 完整原始 profile，字段不够用时兜底，不用重新抓包
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    synced_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TgClassifyCache(Base):
    __tablename__ = "tg_classify_cache"
    __table_args__ = (UniqueConstraint("account_id", "target", "msg_id", name="uq_tg_classify"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target: Mapped[str] = mapped_column(String(128), nullable=False)
    msg_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    keep: Mapped[bool] = mapped_column(Boolean, nullable=False)
    tag: Mapped[str] = mapped_column(String(32), default="")
    reason: Mapped[str] = mapped_column(String(128), default="")
    classified_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Resume(Base):
    """个人求职 app 的简历库：上传后统一转成 Markdown，给本机模型当底稿。"""

    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    markdown: Mapped[str] = mapped_column(Text, default="")  # 原稿
    final_markdown: Mapped[str] = mapped_column(Text, default="")  # SOP 优化后的最终稿
    source_name: Mapped[str] = mapped_column(String(256), default="")
    source_format: Mapped[str] = mapped_column(String(16), default="md")
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ResumeVersion(Base):
    """简历版本：原稿不动，每次采纳建议落一版，可看可删可切当前。"""

    __tablename__ = "resume_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    markdown: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(String(256), default="")
    model: Mapped[str] = mapped_column(String(16), default="")
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ResumeAnalysis(Base):
    """一次 SOP 分析落一份报告，可看可删可改标题。"""

    __tablename__ = "resume_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sop_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sop_name: Mapped[str] = mapped_column(String(128), default="")
    title: Mapped[str] = mapped_column(String(128), default="")
    findings: Mapped[dict] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ResumeSuggestion(Base):
    """一轮优化建议：待定 / 采纳 / 不采纳。"""

    __tablename__ = "resume_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_id: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(16), default="")
    title: Mapped[str] = mapped_column(String(128), default="")
    quote: Mapped[str] = mapped_column(String(256), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    kind: Mapped[str] = mapped_column(String(16), default="optimize")  # analysis | optimize
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ResumeSop(Base):
    """一份 SOP 方案只对应一份分析报告。draft 可改，跑过分析就 used。"""

    __tablename__ = "resume_sops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    resume_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    brief: Mapped[str] = mapped_column(Text, default="")
    models: Mapped[dict] = mapped_column(JSON, default=list)
    steps: Mapped[dict] = mapped_column(JSON, default=list)
    purpose: Mapped[str] = mapped_column(String(16), default="analyze")  # analyze | optimize
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | used
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ValueTag(Base):
    """标签管理：用户拿大白话描述一个信号，本机 AI 转成正则规则，人工确认后才参与打分。
    跟 core/resume.py 里硬编码的 PREFERENCE_RULES 是两套并行机制：那套是「简历/技术栈贴合」，
    这套是用户自己可维护的信号库，按 category 分维度（目前只有"价值观"一个维度，
    结构上留了口子给以后加别的维度），不写死在代码里。
    """

    __tablename__ = "value_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(32), default="价值观")  # 标签所属维度
    description: Mapped[str] = mapped_column(Text, nullable=False)  # 用户原话
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    pattern: Mapped[str] = mapped_column(String(512), nullable=False)  # 正则，大小写不敏感
    polarity: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 正面 / 0 中性 / -1 负面
    weight: Mapped[int] = mapped_column(Integer, nullable=False)  # 5-30
    rationale: Mapped[str] = mapped_column(Text, default="")  # AI 生成时给的解释，供人工确认时参考
    status: Mapped[str] = mapped_column(String(16), default="draft")  # draft | approved
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)  # True：每条职位都露出；加分标签未命中打红，减分标签未命中打绿
    salary_below_usd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 非空时这条标签不用 pattern 正则判断，改成"披露的年薪折算 USD 低于这个数就命中"
    # （没披露薪资的职位一律不算命中——没数据不等于低薪，不能瞎猜）
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class JobValueTag(Base):
    """某条职位被补充打上的标签——跟正则自动命中是两回事，独立于打分规则，
    source 区分历史人工选择（manual）、详情页 AI 辅助（ai_assist）和录入 AI（ai_ingest）。
    参与价值观打分（跟自动命中同等对待），但不受正则约束。
    """

    __tablename__ = "job_value_tags"
    __table_args__ = (UniqueConstraint("channel", "external_id", "tag_id", name="uq_job_value_tag"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tag_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="manual")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class JobQualityReport(Base):
    """职位文本质量痕迹：可疑/高置信问题都记一笔，可溯源。

    severity=block 才会把 scraped_jobs.data_quality_ok 打成 False（列表默认藏）；
    severity=suspect 只报案，不删不藏，避免误杀有效 JD。
    """

    __tablename__ = "job_quality_reports"
    __table_args__ = (
        UniqueConstraint("channel", "external_id", "kind", name="uq_job_quality_report"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    scraped_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # block | suspect
    reason: Mapped[str] = mapped_column(String(256), default="")
    evidence: Mapped[str] = mapped_column(String(512), default="")
    source: Mapped[str] = mapped_column(String(32), default="rule")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class JobRule(Base):
    """系统硬规则表：匹配分权重/栈证据/硬顶、质量 block|suspect、召回信号。

    跟 value_tags（用户可维护的价值观标签）分开：本表是产品口径，改权重/正则走这里，
    业务代码统一 app.core.job_rules 读取，禁止再在各处写死正则。
    """

    __tablename__ = "job_rules"
    __table_args__ = (UniqueConstraint("category", "key", name="uq_job_rule"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    # match_config | match_stack | match_signal | match_cap | match_verdict
    # | quality_block | quality_suspect | recall
    key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(128), default="")
    pattern: Mapped[str] = mapped_column(String(1024), default="")
    weight: Mapped[int] = mapped_column(Integer, default=0)
    severity: Mapped[str] = mapped_column(String(16), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    rationale: Mapped[str] = mapped_column(Text, default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
