import json

import pytest
from security.keychain import ENV_ROOT_KEY, KeychainUnavailable, RootKeyStore
from security.vault import SecretVault


class FakeRootKeyStore:
    def __init__(self, state=None):
        self.state = state if state is not None else {"active": None, "staged": {}}
        self.fail_promote = False

    def validate_rotation_id(self, rotation_id):
        if len(rotation_id) != 32 or any(c not in "0123456789abcdef" for c in rotation_id):
            raise ValueError("invalid root-key rotation id")
        return rotation_id

    def get(self):
        return self.state["active"]

    def get_or_create(self):
        if self.state["active"] is None:
            self.state["active"] = b"a" * 32
        return self.state["active"]

    def stage_rotation(self, rotation_id):
        return self.state["staged"].setdefault(rotation_id, b"b" * 32)

    def get_staged(self, rotation_id):
        return self.state["staged"].get(rotation_id)

    def promote_staged(self, rotation_id):
        if self.fail_promote:
            raise KeychainUnavailable("injected promotion failure")
        key = self.state["staged"].get(rotation_id)
        if key is None:
            raise KeychainUnavailable("staged root key is unavailable")
        self.state["active"] = key
        return key

    def discard_staged(self, rotation_id):
        self.state["staged"].pop(rotation_id, None)


def test_vault_encrypts_and_rotates(tmp_path):
    p = tmp_path / "v.json"
    v = SecretVault(p, "old")
    v.set("token", "secret-value")
    assert "secret-value" not in p.read_text()
    assert SecretVault(p, "old").get("token") == "secret-value"
    v.rotate_password("new")
    assert SecretVault(p, "new").get("token") == "secret-value"
    with pytest.raises(Exception):
        SecretVault(p, "old")


def test_root_key_rotation_changes_key_and_preserves_data(tmp_path):
    state = {"active": b"a" * 32, "staged": {}}
    p = tmp_path / "v.json"
    v = SecretVault(p, root_key_store=FakeRootKeyStore(state))
    v.set("token", "secret-value")
    before = p.read_text()

    v.rotate_root_key()

    assert state["active"] == b"b" * 32
    assert state["staged"] == {}
    assert p.read_text() != before
    assert SecretVault(p, root_key_store=FakeRootKeyStore(state)).get("token") == "secret-value"
    assert not p.with_suffix(".json.rotation").exists()


def test_crash_before_ciphertext_commit_keeps_old_key_readable(tmp_path, monkeypatch):
    state = {"active": b"a" * 32, "staged": {}}
    p = tmp_path / "v.json"
    v = SecretVault(p, root_key_store=FakeRootKeyStore(state))
    v.set("token", "secret-value")
    original = p.read_text()

    def fail_write(_text):
        raise OSError("injected crash before replace")

    monkeypatch.setattr(v, "_atomic_write_text", fail_write)
    with pytest.raises(OSError, match="injected crash"):
        v.rotate_root_key()

    assert p.read_text() == original
    assert state["active"] == b"a" * 32
    assert state["staged"]

    recovered = SecretVault(p, root_key_store=FakeRootKeyStore(state))
    assert recovered.get("token") == "secret-value"
    assert state["active"] == b"a" * 32
    assert state["staged"] == {}
    assert not p.with_suffix(".json.rotation").exists()


def test_crash_after_ciphertext_commit_recovers_staged_key(tmp_path):
    state = {"active": b"a" * 32, "staged": {}}
    p = tmp_path / "v.json"
    store = FakeRootKeyStore(state)
    v = SecretVault(p, root_key_store=store)
    v.set("token", "secret-value")
    store.fail_promote = True

    with pytest.raises(KeychainUnavailable, match="injected promotion failure"):
        v.rotate_root_key()

    rotation_id = json.loads(p.read_text())["root_key_rotation"]
    assert state["active"] == b"a" * 32
    assert state["staged"][rotation_id] == b"b" * 32
    assert p.with_suffix(".json.rotation").exists()

    recovery_store = FakeRootKeyStore(state)
    recovered = SecretVault(p, root_key_store=recovery_store)
    assert recovered.get("token") == "secret-value"
    assert state["active"] == b"b" * 32
    assert state["staged"] == {}
    assert not p.with_suffix(".json.rotation").exists()


def test_restart_after_promotion_before_cleanup_is_readable(tmp_path):
    state = {"active": b"a" * 32, "staged": {}}
    p = tmp_path / "v.json"
    v = SecretVault(p, root_key_store=FakeRootKeyStore(state))
    v.set("token", "secret-value")

    rotation_id = "0" * 32
    journal = p.with_suffix(".json.rotation")
    journal.write_text(json.dumps({"version": 1, "rotation_id": rotation_id}))
    new_key = FakeRootKeyStore(state).stage_rotation(rotation_id)
    v._root_key_rotation = rotation_id
    v._save(master_key=new_key)
    FakeRootKeyStore(state).promote_staged(rotation_id)

    recovered = SecretVault(p, root_key_store=FakeRootKeyStore(state))
    assert recovered.get("token") == "secret-value"
    assert state["active"] == b"b" * 32
    assert state["staged"] == {}
    assert not journal.exists()


def test_existing_ciphertext_never_creates_replacement_root_key(tmp_path):
    state = {"active": b"a" * 32, "staged": {}}
    p = tmp_path / "v.json"
    v = SecretVault(p, root_key_store=FakeRootKeyStore(state))
    v.set("token", "secret-value")
    state["active"] = None

    with pytest.raises(KeychainUnavailable, match="unavailable"):
        SecretVault(p, root_key_store=FakeRootKeyStore(state))
    assert state["active"] is None


def test_committed_rotation_without_matching_staged_key_fails_closed(tmp_path):
    state = {"active": b"a" * 32, "staged": {}}
    p = tmp_path / "v.json"
    v = SecretVault(p, root_key_store=FakeRootKeyStore(state))
    v.set("token", "secret-value")

    rotation_id = "1" * 32
    new_key = b"c" * 32
    p.with_suffix(".json.rotation").write_text(
        json.dumps({"version": 1, "rotation_id": rotation_id})
    )
    v._root_key_rotation = rotation_id
    v._save(master_key=new_key)

    with pytest.raises(KeychainUnavailable, match="no recoverable staged"):
        SecretVault(p, root_key_store=FakeRootKeyStore(state))
    assert state["active"] == b"a" * 32


def test_invalid_rotation_journal_fails_closed(tmp_path):
    state = {"active": b"a" * 32, "staged": {}}
    p = tmp_path / "v.json"
    v = SecretVault(p, root_key_store=FakeRootKeyStore(state))
    v.set("token", "secret-value")
    p.with_suffix(".json.rotation").write_text("not-json")

    with pytest.raises(RuntimeError, match="invalid SecretVault root-key rotation journal"):
        SecretVault(p, root_key_store=FakeRootKeyStore(state))


def test_password_backed_vault_rejects_root_key_rotation(tmp_path):
    v = SecretVault(tmp_path / "v.json", "password")
    with pytest.raises(RuntimeError, match="password-backed"):
        v.rotate_root_key()


def test_crash_after_key_promotion_before_marker_cleanup_recovers(tmp_path, monkeypatch):
    state = {"active": b"a" * 32, "staged": {}}
    p = tmp_path / "v.json"
    v = SecretVault(p, root_key_store=FakeRootKeyStore(state))
    v.set("token", "secret-value")
    original_write = v._atomic_write_text
    calls = 0

    def fail_second_rotation_write(text):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected crash during marker cleanup")
        original_write(text)

    monkeypatch.setattr(v, "_atomic_write_text", fail_second_rotation_write)
    with pytest.raises(OSError, match="marker cleanup"):
        v.rotate_root_key()

    assert state["active"] == b"b" * 32
    assert state["staged"]
    assert p.with_suffix(".json.rotation").exists()

    recovered = SecretVault(p, root_key_store=FakeRootKeyStore(state))
    assert recovered.get("token") == "secret-value"
    assert state["active"] == b"b" * 32
    assert state["staged"] == {}
    assert not p.with_suffix(".json.rotation").exists()


def test_environment_managed_root_key_cannot_be_staged_for_rotation(monkeypatch):
    import base64

    monkeypatch.setenv(ENV_ROOT_KEY, base64.b64encode(b"e" * 32).decode())
    store = RootKeyStore()

    with pytest.raises(KeychainUnavailable, match="environment-managed"):
        store.stage_rotation("0" * 32)
