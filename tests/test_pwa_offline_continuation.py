from __future__ import annotations

from pathlib import Path


def test_pwa_continuation_cache_is_bounded_and_non_authoritative():
    source = Path('pwa/data-plane-offline.js').read_text(encoding='utf-8')
    assert 'MAX_ITEM_BYTES=64*1024' in source
    assert 'MAX_OUTBOX=500' in source
    assert "raw_file_bytes_stored:false" in source
    assert "secrets_stored:false" in source
    assert "authoritative:false" in source
    assert "'file_bytes'" in source
    assert "'api_key'" in source
    assert "'access_token'" in source
    assert 'indexedDB.open' in source


def test_service_worker_never_caches_private_api_responses():
    source = Path('pwa/sw.js').read_text(encoding='utf-8')
    assert "url.pathname.startsWith('/iphone/api/')" in source
    assert "url.pathname.startsWith('/dashboard/')" in source
    assert "url.pathname.startsWith('/cloud/')" in source
    assert "if(event.request.method!=='GET'||privateDataPath)return" in source
    assert "'/iphone/data-plane-offline.js'" in source
