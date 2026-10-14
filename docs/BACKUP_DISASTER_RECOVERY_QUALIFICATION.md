# Backup and disaster-recovery qualification

The qualification suite exercises encrypted local backups and portable disaster-recovery bundles through the existing BackupService and DisasterRecoveryService.

It verifies authenticated backup round trips, legacy v1 ZIP restore compatibility, wrong-key and corruption refusal without changing healthy target data, rollback after an interrupted multi-file restore, and clean-host recovery of encrypted MemoryStore content. The clean-host scenario rotates the source root key, restores under a different host root key, and checks that the DEK remains wrapped in the portable bundle and is rewrapped under the target SecretVault before the database is exposed.

Universal identity metadata is carried inside the encrypted backup manifest and therefore inside portable disaster-recovery bundles. Cross-host restore preserves the same `owner_id` and `vishnu_id` while excluding the source `owner-access.sqlite3` authority. The owner must reconfigure authentication and register the restored host as a new trusted device; source device credentials are never cloned.

Ordinary backups remain protected by the source installation's RootKeyStore. Portable disaster-recovery bundles use a random owner-held recovery key to wrap the MemoryStore DEK for transport; the DEK is never stored plaintext. The desktop Settings flow exports the data bundle and a separate AES-GCM encrypted key file. The key file uses scrypt with a random salt; the owner must retain the independent passphrase. First-run restore validates both files and the passphrase, then stages only a key envelope encrypted by the target host's RootKeyStore. Plain recovery key bytes are not persisted across restart. Restore runs before the next runtime starts and remains gated by maintenance mode. Security-authority databases are skipped and must be rebound on the target host.

The recovery package header contains the stable, non-secret `owner_id` so restore can verify the owner binding before the target has restored identity metadata. The encrypted payload's identity metadata must match this owner ID. It does not contain a source device key, active session, or owner credential.

Run the focused qualification with:

```sh
pytest -q tests/test_disaster_recovery.py tests/test_backup_recovery_qualification.py
```


## Error-injection evidence

The focused suite also injects a failure at the backup's final atomic replace and verifies the prior archive remains readable with no temporary payload left behind. It creates valid outer recovery bundles containing deliberately modified portable MemoryStore key envelopes (wrapped key, owner binding, and key identifier) and verifies restore refuses before changing the target.

The repository-wide qualification also runs SQLite migration fault/rollback/retry coverage from `tests/test_sqlite_foundation.py` and `tests/test_memory_store_migrations.py`, approval expiry/replay checks, and simulated device disconnect/timeout checks.
