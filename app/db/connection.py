from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


def _build_engine():
    if settings.turso_database_url:
        host = settings.turso_database_url.replace("libsql://", "", 1)
        url = f"sqlite+libsql://{host}?secure=true"
        return create_engine(url, connect_args={"auth_token": settings.turso_auth_token})

    if settings.database_url:
        url = settings.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return create_engine(url, pool_pre_ping=True)

    return None


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine) if engine else None


def get_db() -> Session | None:
    if not SessionLocal:
        return None
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
