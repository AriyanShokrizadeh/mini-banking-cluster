"""SQLAlchemy models for YSQL-compatible banking persistence."""

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from banking.infrastructure.database import Base


class TimestampMixin:
    """Provide a database-generated creation timestamp."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


class Account(Base):
    """Account balances stored in minor currency units."""

    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint("opening_balance_minor >= 0", name="opening_nonnegative"),
        CheckConstraint("balance_minor >= 0", name="balance_nonnegative"),
    )

    account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    opening_balance_minor: Mapped[int] = mapped_column(BigInteger)
    balance_minor: Mapped[int] = mapped_column(BigInteger)


class Operation(TimestampMixin, Base):
    """Persist successful financial operations."""

    __tablename__ = "operations"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="operation_positive_amount"),
        CheckConstraint(
            "action IN ('deposit', 'withdraw')",
            name="operation_valid_action",
        ),
    )

    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("accounts.account_id"),
    )

    action: Mapped[str] = mapped_column(String(16))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    request_hash: Mapped[str] = mapped_column(String(64))
    result_balance_minor: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default="success")


class LedgerEntry(TimestampMixin, Base):
    """Record the balance change produced by a successful operation."""

    __tablename__ = "ledger_entries"
    __table_args__ = (CheckConstraint("delta_minor <> 0", name="ledger_nonzero_delta"),)

    entry_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("operations.request_id"),
        unique=True,
    )
    account_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("accounts.account_id"),
    )

    delta_minor: Mapped[int] = mapped_column(BigInteger)
    balance_after_minor: Mapped[int] = mapped_column(BigInteger)


class RequestReceipt(TimestampMixin, Base):
    """Persist idempotency claims and final request outcomes."""

    __tablename__ = "request_receipts"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="receipt_positive_amount"),
        CheckConstraint(
            "action IN ('deposit', 'withdraw')",
            name="receipt_valid_action",
        ),
        CheckConstraint(
            "status IN ('pending', 'success', 'error')",
            name="receipt_valid_status",
        ),
    )

    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    account_id: Mapped[str] = mapped_column(String(64))

    action: Mapped[str] = mapped_column(String(16))
    amount_minor: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16))

    result_balance_minor: Mapped[int | None] = mapped_column(BigInteger)
    error_code: Mapped[str | None] = mapped_column(String(64))


class HealthProbe(Base):
    """Track committed write probes independently of financial data."""

    __tablename__ = "health_probes"

    instance_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger)
