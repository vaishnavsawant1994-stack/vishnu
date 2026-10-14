from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from security.owner_access import FirstRunClaimBusy, OwnerAccessStore


def _run_concurrently(worker, count: int):
    barrier = Barrier(count)

    def invoke():
        barrier.wait(timeout=10)
        return worker()

    with ThreadPoolExecutor(max_workers=count) as pool:
        return [future.result(timeout=20) for future in [pool.submit(invoke) for _ in range(count)]]


def test_recovery_code_is_consumed_exactly_once_under_concurrency(tmp_path):
    store = OwnerAccessStore(tmp_path / 'owner-access.sqlite3')
    code = store.regenerate_recovery_codes(count=4)[0]
    before = store.recovery_codes_remaining()

    results = _run_concurrently(lambda: store.consume_recovery_code(code), 4)

    assert results.count(True) == 1
    assert results.count(False) == 3
    assert store.recovery_codes_remaining() == before - 1
    assert store.consume_recovery_code(code) is False


def test_webauthn_challenge_is_consumed_exactly_once_under_concurrency(tmp_path):
    store = OwnerAccessStore(tmp_path / 'owner-access.sqlite3')
    challenge_id = store.create_challenge(
        'authentication',
        b'one-time-challenge',
        'vishnu.local',
        'https://vishnu.local',
        device_id='device-1',
    )

    results = _run_concurrently(
        lambda: store.consume_challenge(challenge_id, 'authentication', device_id='device-1'),
        8,
    )

    claimed = [result for result in results if result is not None]
    assert len(claimed) == 1
    assert claimed[0]['id'] == challenge_id
    assert claimed[0]['challenge'] == b'one-time-challenge'
    assert store.consume_challenge(challenge_id, 'authentication', device_id='device-1') is None


def test_first_run_claim_allows_one_creation_client_and_same_client_retry(tmp_path):
    store = OwnerAccessStore(tmp_path / 'owner-access.sqlite3')
    claim, created = store.acquire_first_run_claim()
    assert created is True
    assert store.acquire_first_run_claim(claim) == (claim, False)
    with pytest.raises(FirstRunClaimBusy):
        store.acquire_first_run_claim()
    assert store.release_first_run_claim(claim) is True
    assert store.acquire_first_run_claim()[1] is True


def test_first_run_claim_race_has_one_winner(tmp_path):
    store = OwnerAccessStore(tmp_path / 'owner-access.sqlite3')

    def reserve():
        try:
            return store.acquire_first_run_claim()[1]
        except FirstRunClaimBusy:
            return False

    outcomes = _run_concurrently(reserve, 8)
    assert outcomes.count(True) == 1
    assert outcomes.count(False) == 7
