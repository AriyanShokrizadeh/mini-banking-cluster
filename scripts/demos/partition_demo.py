"""Manual network-partition demo (financial results do not prove Raft quorum)."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from time import sleep
from uuid import UUID, uuid4

import httpx2

from client.banking_client import BankingClient


def deposit(server: str, account: str, amount: int, request_id: UUID, timeout: float) -> str:
    try:
        with BankingClient(server, timeout=timeout, retries=0) as client:
            client.transact("deposit", account, amount, request_id=request_id)
        return "confirmed"
    except httpx2.RequestError:
        return "unknown"
    except httpx2.HTTPStatusError as exc:
        return "unknown" if exc.response.status_code >= 500 else "rejected"


def run_demo(
    server: str,
    account: str,
    *,
    count: int,
    amount: int,
    workers: int,
    interval: float,
    recovery_wait: float,
    timeout: float,
    on_progress: Callable[[int], None] | None = None,
    before_reconcile: Callable[[], None] | None = None,
    on_begin: Callable[[list[str]], None] | None = None,
) -> dict[str, object]:
    with BankingClient(server, timeout=timeout) as client:
        before = int(client.balance(account)["balance"])
    ids = [uuid4() for _ in range(count)]
    if on_begin:
        on_begin([str(item) for item in ids])
    print("Apply the partition on VM1 while deposits are sent.", flush=True)
    for request_id in ids:
        print(request_id, flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = []
        for number, request_id in enumerate(ids, 1):
            futures.append(pool.submit(deposit, server, account, amount, request_id, timeout))
            if interval:
                sleep(interval)
            if on_progress:
                on_progress(number)
        results = dict(zip(ids, (future.result() for future in futures)))

    print("Restore the network before reconciliation.", flush=True)
    if before_reconcile:
        before_reconcile()
    else:
        sleep(recovery_wait)
    for request_id in ids:
        if results[request_id] == "unknown":
            results[request_id] = deposit(server, account, amount, request_id, timeout)

    with BankingClient(server, timeout=timeout) as client:
        after = int(client.balance(account)["balance"])
    confirmed = sum(value == "confirmed" for value in results.values())
    rejected = sum(value == "rejected" for value in results.values())
    unresolved = [str(i) for i in ids if results[i] == "unknown"]
    expected = before + count * amount
    return {
        "financial_check_passed": confirmed == count and after == expected,
        "quorum_proved": False,
        "before": before,
        "expected": expected,
        "after": after,
        "requested": count,
        "confirmed_after_recovery": confirmed,
        "rejected": rejected,
        "unresolved_ids": unresolved,
        "request_ids": [str(i) for i in ids],
    }
