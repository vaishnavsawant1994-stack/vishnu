# Backup and disaster-recovery qualification

The qualification suite exercises encrypted local backups and portable disaster-recovery bundles through the existing BackupService and DisasterRecoveryService.

It verifies authenticated backup round trips, legacy v1 ZIP restore compatibility, wrong-key and corruption refusal without changing healthy target data, rollback after an interrupted multi-file restore, and clean-host recovery of encrypted MemoryStore content. The clean-host scenario rotates the source root key, restores under a different host root key, and checks that the DEK remains wrapped in the portable bundle and is rewrapped under the target SecretVault before the database is exposed.

Ordinary backups remain protected by the source installation's RootKeyStore. Portable disaster-recovery bundles use the owner-held recovery key to wrap the MemoryStore DEK for transport; the DEK is never stored plaintext. Restore remains gated by maintenance mode and preserves the existing policy that security-authority databases are skipped and must be rebound on the target host.

Run the focused qualification with:

```sh
pytest -q tests/test_disaster_recovery.py tests/test_backup_recovery_qualification.py
```
