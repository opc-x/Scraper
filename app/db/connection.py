import time

from sqlalchemy import create_engine, event
from sqlalchemy.exc import DisconnectionError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from app.core.config import settings

# 空闲超过这个秒数的连接，取出来之前先自己 ping 一次
_IDLE_PING_AFTER = 60


def _build_engine():
    if settings.local_sqlite_path:
        # 本机常驻部署，主存储直接落本地文件——Turso 远程往返 0.2-0.3s/次，
        # 200+ 条批量写入时经常在提交前超时整体回滚（电鸭渠道踩过），本地文件没这问题。
        # 消费方（JobSniper Web / signore）只走 API 不直连 DB，换存储对它们透明；
        # 代价是没有 Turso 现成的异地备份，得另外定期同步一份出去。
        engine = create_engine(
            f"sqlite:///{settings.local_sqlite_path}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):  # noqa: ARG001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        return engine

    if settings.turso_database_url:
        host = settings.turso_database_url.replace("libsql://", "", 1)
        url = f"sqlite+libsql://{host}?secure=true"
        # libsql 的 Rust 驱动在多连接并发下会在 rollback 时 panic
        # （pyo3_runtime.PanicException: Option::unwrap() on a None value），
        # panic 会毒掉连接池，之后所有请求挂死。限制成单连接串行访问绕开它。
        return create_engine(
            url,
            connect_args={"auth_token": settings.turso_auth_token},
            poolclass=QueuePool,
            pool_size=1,
            max_overflow=0,
            pool_timeout=60,
            # 不能开 pool_pre_ping：SQLAlchemy 的 pre-ping 在 libsql 驱动上每次 checkout
            # 要 ~5.5s，所有非缓存请求都白付这一笔（实测接口 6s → 0.2s）。断连兜底改成
            # 下面的 _install_idle_ping：只有空闲久了才 ping，一次往返 ~0.3s。
            pool_recycle=600,
        )

    if settings.database_url:
        url = settings.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return create_engine(url, pool_pre_ping=True)

    return None


def _install_idle_ping(target) -> None:
    """空闲连接才 ping，热连接直接用。替代慢到不能用的 pool_pre_ping。"""

    @event.listens_for(target, "checkin")
    def _mark_idle(dbapi_conn, record):  # noqa: ARG001
        record.info["last_used"] = time.monotonic()

    @event.listens_for(target, "checkout")
    def _ping_if_idle(dbapi_conn, record, proxy):  # noqa: ARG001
        last_used = record.info.get("last_used")
        if last_used is None or time.monotonic() - last_used < _IDLE_PING_AFTER:
            return
        try:
            cursor = dbapi_conn.cursor()
            cursor.execute("select 1")
            cursor.fetchall()
            cursor.close()
        except Exception as exc:  # 连接已死，让连接池丢掉它并重连后重试本次 checkout
            raise DisconnectionError(str(exc)) from exc


engine = _build_engine()
if engine is not None and settings.turso_database_url:
    _install_idle_ping(engine)
SessionLocal = sessionmaker(bind=engine) if engine else None


def get_db() -> Session | None:
    if not SessionLocal:
        return None
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
