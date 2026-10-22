"""Expected business errors (not infrastructure failures)."""


class BankingError(Exception):
    code = "BANKING_ERROR"
    http_status = 400


class UnknownAccount(BankingError):
    code = "ACCOUNT_NOT_FOUND"
    http_status = 404


class InsufficientFunds(BankingError):
    code = "INSUFFICIENT_FUNDS"
    http_status = 409


class IdempotencyConflict(BankingError):
    code = "IDEMPOTENCY_CONFLICT"
    http_status = 409


class InvalidAmount(BankingError):
    code = "INVALID_AMOUNT"
    http_status = 422


class UnsupportedAction(BankingError):
    code = "UNSUPPORTED_ACTION"
    http_status = 422
