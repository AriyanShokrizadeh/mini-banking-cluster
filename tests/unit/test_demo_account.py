"""Isolated lab accounts must never overwrite existing balances."""

import pytest
from scripts.setup import create_demo_account as demo
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from banking.infrastructure.models import Account


def test_demo_account_is_new_and_unique(engine: Engine, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(demo, "make_engine", lambda _settings: engine)
    monkeypatch.setattr(demo, "get_settings", lambda: object())
    monkeypatch.setattr(engine, "dispose", lambda: None)

    demo.create_account("DEMO_isolated", 1000)
    with pytest.raises(IntegrityError):
        demo.create_account("DEMO_isolated", 1000)

    with Session(engine) as session:
        assert session.get_one(Account, "DEMO_isolated").balance_minor == 1000
        assert session.get_one(Account, "A1001").balance_minor == 1000


def test_demo_account_rejects_seeded_ids() -> None:
    with pytest.raises(ValueError):
        demo.create_account("A1001", 1000)
