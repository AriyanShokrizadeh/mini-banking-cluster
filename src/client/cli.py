"""Typer commands for banking operations."""

import json
from collections.abc import Callable
from typing import Annotated, Any
from uuid import UUID, uuid4

import httpx2
import typer

from client.banking_client import BankingAction, BankingClient

app = typer.Typer(no_args_is_help=True, help="Mini Banking Cluster (Core Banking)")

DEFAULT_SERVER = "http://127.0.0.1:8000"
ServerOption = Annotated[str, typer.Option("--server")]
RequestIdOption = Annotated[UUID | None, typer.Option("--request-id")]
RetriesOption = Annotated[int, typer.Option("--retries", min=0, max=10)]


def _run(
    server: str,
    operation: Callable[[BankingClient], dict[str, Any]],
    *,
    retries: int = 0,
) -> None:
    """Execute a request and print its JSON response."""
    try:
        with BankingClient(server, retries=retries) as client:
            result = operation(client)
        typer.echo(json.dumps(result, indent=2, ensure_ascii=False))
    except httpx2.HTTPStatusError as exc:
        typer.echo(
            f"Server returned HTTP {exc.response.status_code}: {exc.response.text}",
            err=True,
        )
        raise typer.Exit(code=1) from exc
    except (httpx2.RequestError, ValueError) as exc:
        typer.echo(f"Banking request failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


def _transact(
    action: BankingAction,
    account: str,
    amount: int,
    *,
    server: str,
    request_id: UUID | None,
    retries: int,
) -> None:
    if amount <= 0:
        raise typer.BadParameter("amount must be a positive integer")

    request_id = request_id or uuid4()
    typer.echo(f"request_id={request_id}", err=True)
    _run(
        server,
        lambda client: client.transact(action, account, amount, request_id=request_id),
        retries=retries,
    )


@app.command()
def health(
    server: ServerOption = DEFAULT_SERVER,
    check: Annotated[str, typer.Option("--check")] = "live",
) -> None:
    """Check service availability."""
    match check:
        case "live" | "db" | "ready":
            _run(server, lambda client: client.check(check))
        case _:
            raise typer.BadParameter("--check must be live, db, or ready")


@app.command()
def balance(account: str, server: ServerOption = DEFAULT_SERVER) -> None:
    """Show an account balance."""
    _run(server, lambda client: client.balance(account))


@app.command()
def deposit(
    account: str,
    amount: int,
    server: ServerOption = DEFAULT_SERVER,
    request_id: RequestIdOption = None,
    retries: RetriesOption = 0,
) -> None:
    """Deposit money into an account."""
    _transact(
        "deposit",
        account,
        amount,
        server=server,
        request_id=request_id,
        retries=retries,
    )


@app.command()
def withdraw(
    account: str,
    amount: int,
    server: ServerOption = DEFAULT_SERVER,
    request_id: RequestIdOption = None,
    retries: RetriesOption = 0,
) -> None:
    """Withdraw money from an account."""
    _transact(
        "withdraw",
        account,
        amount,
        server=server,
        request_id=request_id,
        retries=retries,
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()
