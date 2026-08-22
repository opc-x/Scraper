from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import telegram_client
from app.db.schema import Base


def test_telegram_account_crud_uses_portable_orm(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(telegram_client, "SessionLocal", session_factory)

    account_id = telegram_client.create_account("main", "+86123", "42", "secret")
    account = telegram_client.get_account(account_id)

    assert account["label"] == "main"
    assert account["session_str"] == ""
    assert telegram_client.list_accounts()[0]["has_session"] is False

    telegram_client.update_account(account_id, session_str="session", is_active=False)
    updated = telegram_client.get_account(account_id)
    assert updated["session_str"] == "session"
    assert updated["is_active"] is False

    telegram_client.delete_account(account_id)
    assert telegram_client.list_accounts() == []
