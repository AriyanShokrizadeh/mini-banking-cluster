"""Create a small fixed set of lab accounts once, without overwriting existing data.

Run on a banking VM with BANKING_DATABASE_URL from its protected EnvironmentFile.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from banking.config import get_settings
from banking.infrastructure.database import make_engine
from banking.infrastructure.models import Account

LAB_ACCOUNTS = (
    "DEMO_LAB_BASIC",
    "DEMO_LAB_CONCURRENCY",
    "DEMO_LAB_DURABILITY",
    "DEMO_LAB_FAILOVER",
    "DEMO_LAB_PARTITION",
)


def prepare(engine) -> None:
    with Session(engine) as session, session.begin():
        session.add_all(
            Account(account_id=account_id, opening_balance_minor=1000, balance_minor=1000)
            for account_id in LAB_ACCOUNTS
            if session.get(Account, account_id) is None
        )
        accounts = session.scalars(
            select(Account).where(Account.account_id.in_(LAB_ACCOUNTS))
        ).all()
        if len(accounts) != len(LAB_ACCOUNTS):
            raise RuntimeError("Fixed account pool could not be prepared")
        for account in accounts:
            if account.opening_balance_minor != 1000:
                raise RuntimeError(f"Unexpected original balance for {account.account_id}")
    print("Fixed lab accounts ready (existing balances and history preserved).")


def main() -> None:
    engine = make_engine(get_settings())
    try:
        prepare(engine)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
