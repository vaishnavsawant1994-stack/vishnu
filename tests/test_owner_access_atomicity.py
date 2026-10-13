from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from security.owner_access import OwnerAccessStore


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
