# Sensitive data at rest

MemoryStore uses authenticated field encryption for owner-authored content. The
DEK is a purpose-specific value stored by the canonical `SecretVault`; it is
not a second root key. `RootKeyStore` protects the vault. AES-256-GCM authenticates
each field with component, table, row ID, column, and envelope version as AAD.

| Class | Stored fields | Storage rule |
| --- | --- | --- |
| Credentials and authentication secrets | Provider credentials and other existing secret material | Continue to use `SecretVault`; never move into ordinary MemoryStore encryption. |
| Highly sensitive content | Message content; memory subject/content/evidence/metadata; task payload; audit payload; memory-use query | AES-GCM field envelope. |
| Sensitive, operationally useful content | Message metadata; memory source/tags; task title; conflict reason | AES-GCM field envelope. |
| Structural metadata | IDs, roles/types, timestamps, confidence/status/sensitivity enums, relationships, foreign keys, migration state, memory preferences | Plaintext for indexing, authorization, lifecycle, and migration behavior. |

Memory subjects have a keyed HMAC blind index for exact active-subject lookup.
The index is derived from the MemoryStore DEK with a separate HKDF purpose and
does not store the normalized subject. General memory search decrypts a bounded
candidate set locally and preserves substring matching.

Migration 4 upgrades legacy plaintext rows transactionally. It recognizes only
the versioned `v1:` envelope marker, verifies already-encrypted fields instead
of wrapping them again, and fails if the existing key is missing or wrong.
MemoryStore connections enable SQLite `secure_delete` so replaced plaintext is
not retained in freed table cells. Domain APIs return plaintext only after
successful authenticated decryption.

The regular backup excludes `vault.json`. To preserve encrypted MemoryStore
data, it adds a distinct AES-GCM-wrapped DEK envelope to the already encrypted
backup payload. Restore validates the envelope before replacing files and
stores the recovered DEK through the canonical SecretVault. The plaintext DEK
is never serialized into the backup. Root-key availability remains required by
the existing encrypted backup format.
