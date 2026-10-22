"""Manual failover demo: stop Banking A while deposits reach HAProxy."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from time import sleep
from uuid import UUID, uuid4

import httpx2

from client.banking_client import BankingClient


def deposit(client: BankingClient, account: str, amount: int, request_id: UUID) -> bool:
    try:
        client.transact("deposit", account, amount, request_id=request_id)
        return True
    except httpx2.HTTPError:
        return False


def run_demo(
    server: str,
    account: str,
    *,
    count: int,
    amount: int,
    interval: float,
    retries: int,
    workers: int = 1,
    on_progress: Callable[[int], None] | None = None,
    before_reconcile: Callable[[], None] | None = None,
    on_begin: Callable[[list[str]], None] | None = None,
) -> dict[str, object]:
    ids = [uuid4() for _ in range(count)]
    if on_begin:
        on_begin([str(item) for item in ids])
    results: dict[UUID, bool] = {}
    with BankingClient(server, timeout=3, retries=0) as client:
        before = int(client.balance(account)["balance"])
        first_backend = client.check("live")["instance"]

    print(f"Start: {first_backend}, balance={before}", flush=True)
    print("Stop Banking A during these requests:", flush=True)
    for request_id in ids:
        print(request_id, flush=True)

    def send(request_id: UUID) -> bool:
        with BankingClient(server, timeout=3, retries=0) as worker:
            return deposit(worker, account, amount, request_id)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        if on_progress is not None and workers == 1:
            # Only stream in manual-control mode: do not queue the whole batch
            # before the callback can stop the primary.
            for number, request_id in enumerate(ids, 1):
                results[request_id] = pool.submit(send, request_id).result()
                print(
                    f"{number}/{count} | {request_id} | "
                    f"{'OK' if results[request_id] else 'UNKNOWN'}",
                    flush=True,
                )
                on_progress(number)
                if interval:
                    sleep(interval)
        else:
            futures = []
            for request_id in ids:
                futures.append(pool.submit(send, request_id))
                if interval:
                    sleep(interval)
            for number, (request_id, future) in enumerate(zip(ids, futures), 1):
                results[request_id] = future.result()
                print(
                    f"{number}/{count} | {request_id} | "
                    f"{'OK' if results[request_id] else 'UNKNOWN'}",
                    flush=True,
                )
                if on_progress:
                    on_progress(number)

    if before_reconcile:
        before_reconcile()
    confirmed = sum(results.values())
    with BankingClient(server, timeout=5, retries=retries) as client:
        for request_id in ids:
            if not results[request_id]:
                results[request_id] = deposit(client, account, amount, request_id)
        last_backend = client.check("live")["instance"]
        after = int(client.balance(account)["balance"])
        successful = next((request_id for request_id in ids if results[request_id]), None)
        replay_ok = False
        if successful:
            replay = client.transact("deposit", account, amount, request_id=successful)
            replay_ok = replay.get("replayed") is True
        after_replay = int(client.balance(account)["balance"])

    unresolved = [str(i) for i in ids if not results[i]]
    expected = before + count * amount
    return {
        "passed": (
            not unresolved
            and after == expected == after_replay
            and replay_ok
            and first_backend == "banking-a"
            and last_backend == "banking-b"
        ),
        "initial_instance": first_backend,
        "final_instance": last_backend,
        "before": before,
        "after": after,
        "after_replay": after_replay,
        "expected": expected,
        "attempted": count,
        "confirmed": confirmed,
        "recovered": sum(results.values()) - confirmed,
        "replay_verified": replay_ok,
        "unresolved_ids": unresolved,
        "request_ids": [str(i) for i in ids],
    }
