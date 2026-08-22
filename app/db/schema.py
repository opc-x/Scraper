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
