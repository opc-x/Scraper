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
