from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_pwa_continuation_cache_executes_ttl_expiry_and_quota_eviction_contracts():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is not installed in this test environment')

    script = r"""
import {
  VISHNU_CONTINUATION_LIMITS,
  boundedContinuationTtl,
  continuationPrunePlan,
} from './pwa/data-plane-cache.js';

function assert(condition,message){if(!condition)throw new Error(message);}
const limits=VISHNU_CONTINUATION_LIMITS;
assert(limits.maxEntries===512,'entry bound changed unexpectedly');
assert(limits.maxTotalBytes===8*1024*1024,'total byte bound changed unexpectedly');
assert(limits.maxRecordBytes===64*1024,'record byte bound changed unexpectedly');
assert(limits.maxTtlMs===7*24*60*60*1000,'TTL bound changed unexpectedly');
assert(limits.minTtlMs===60_000,'minimum TTL changed unexpectedly');
assert(boundedContinuationTtl(1)===60_000,'short TTL must clamp to one minute');
assert(boundedContinuationTtl(limits.maxTtlMs*2)===limits.maxTtlMs,'TTL must not exceed seven days');
assert(boundedContinuationTtl(undefined)===limits.maxTtlMs,'default TTL must be seven days');

const now=1_000_000;
const plan=continuationPrunePlan([
  {globalId:'expired',expiresAt:now-1,lastAccess:1,storedBytes:10},
  {globalId:'oldest',expiresAt:now+1000,lastAccess:2,storedBytes:40},
  {globalId:'middle',expiresAt:now+1000,lastAccess:3,storedBytes:40},
  {globalId:'newest',expiresAt:now+1000,lastAccess:4,storedBytes:40},
],{now,maxEntries:2,maxTotalBytes:100});
assert(plan.removeIds.includes('expired'),'expired rows must be evicted');
assert(plan.removeIds.includes('oldest'),'LRU row must be evicted to satisfy entry/byte quota');
assert(plan.remainingEntries===2,'entry quota must be enforced');
assert(plan.remainingBytes===80,'byte accounting must exclude evicted rows');

const bytePlan=continuationPrunePlan([
  {globalId:'a',expiresAt:now+1000,lastAccess:1,storedBytes:5*1024*1024},
  {globalId:'b',expiresAt:now+1000,lastAccess:2,storedBytes:4*1024*1024},
],{now,maxEntries:10,maxTotalBytes:limits.maxTotalBytes});
assert(bytePlan.removeIds.length===1 && bytePlan.removeIds[0]==='a','oldest row must be evicted when byte quota is exceeded');
assert(bytePlan.remainingBytes===4*1024*1024,'remaining bytes must be within quota');
console.log('pwa-cache-bounds-ok');
"""
    result = subprocess.run(
        [node, '--experimental-default-type=module', '--eval', script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert 'pwa-cache-bounds-ok' in result.stdout
