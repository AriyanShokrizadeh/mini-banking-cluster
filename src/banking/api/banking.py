from fastapi import APIRouter, Request
from sqlalchemy.orm import Session

from banking.api.dependencies import EngineDependency, SessionDependency
from banking.api.schemas import AccountID, BalanceOut, TransactionIn, TransactionOut
from banking.application.retry import execute_transaction
from banking.application.service import BankingService
from banking.domain.models import TransactionResult

router = APIRouter(prefix="/api/v1", tags=["Banking"])


@router.get(
    "/accounts/{account_id}/balance",
    response_model=BalanceOut,
    name="balance",
)
def get_account_balance(
    account_id: AccountID,
    request: Request,
    session: SessionDependency,
) -> BalanceOut:
    request.state.action = "balance"
    request.state.account_id = account_id

    balance = BankingService(session).get_balance(account_id)
    return BalanceOut(account=account_id, balance=balance)


@router.post(
    "/transactions",
    response_model=TransactionOut,
    name="transaction",
)
def create_transaction(
    payload: TransactionIn,
    request: Request,
    engine: EngineDependency,
) -> TransactionOut:
    request_id = str(payload.request_id)
    request.state.action = payload.action
    request.state.account_id = payload.account
    request.state.financial_request_id = request_id

    def transact(session: Session) -> TransactionResult:
        return BankingService(session).transact(
            request_id=request_id,
            action=payload.action,
            account=payload.account,
            amount=payload.amount,
        )

    result = execute_transaction(
        engine,
        transact,
        attempts=request.app.state.settings.transaction_retry_attempts,
    )
    return TransactionOut(
        request_id=result.request_id,
        account=result.account,
        balance=result.balance,
        replayed=result.replayed,
    )
