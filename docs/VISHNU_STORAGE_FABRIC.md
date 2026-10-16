# Vishnu Universal Storage Fabric

## Purpose

The storage fabric extends Vishnu's existing local-first data plane. It does not
replace or duplicate the authorities already present in Vishnu.

Canonical authorities remain:

- `data_plane_items`: logical object / residency policy authority.
- `data_plane_locations`: authorized physical replica/location authority.
- `DeviceRegistry` and `DeviceGateway`: device trust and device transport.
- `SecretVault` / envelope key manager: provider credentials and data-key wrapping.
- existing ToolRegistry / approval / owner reauthentication paths: consequential mutation authority.
- existing backup/disaster-recovery services: recovery authority.

The fabric adds provider capability discovery, policy-aware placement previews,
provider health, replica reconciliation, durable provider-transfer checkpoints,
and bounded S3-compatible multipart/range streaming.

## Non-negotiable rule

> My data stays where I decide. Vishnu knows where it is. Vishnu can securely
> reach it when I ask and when it is reachable. Vishnu never silently moves it.
> Cloud is optional. Every trusted device can continue permitted work
> independently.

Reconciliation therefore never creates a replacement cloud/device copy on its
own. It may verify an authorized location, mark a confirmed missing replica, or
mark a provider unreachable. Creating a durable replica still requires the
existing item policy and explicit copy authority.

## Logical objects and replicas

Vishnu already had the correct foundation before this work:

- `data_plane_items` identify a logical object and its policy/version/digest.
- `data_plane_locations` record the devices/providers that are authorized to
  hold that object's bytes.

The storage fabric intentionally reuses those records instead of adding parallel
`LogicalObject` or `StorageReplica` tables.

## Provider capability model

Capabilities describe the adapter Vishnu actually wires, not what the upstream
provider could theoretically do.

For example, S3/R2/B2 are marked range-readable and multipart/resumable because
the storage fabric implements those paths. Google Drive is not marked resumable
until Vishnu's governed Drive bridge itself exposes a resumable streaming path.

This prevents UI/planning code from making unsupported provider claims.

## Placement

`StorageFabric.plan_placement()` is advisory and side-effect free.

It filters candidates through the canonical item policy first, then considers:

- current replica presence
- health
- locality
- latency
- capacity
- cost weight
- failure-domain diversity

Important policy behavior:

- `device_only`: raw bytes remain on the primary device.
- `progress_only`: only the existing bounded progress projection may replicate;
  raw object bytes do not.
- `on_demand`: automatic planning never creates a new provider replica.
- `sync_everywhere`: eligible targets may be proposed, but the preview itself
  never copies bytes.

## Durable provider transfers

The existing lease-bound byte-transfer system remains the trusted-device remote
view/use transport. The storage fabric adds a separate durable provider-transfer
checkpoint ledger for provider object uploads.

Each job has:

- stable job ID and idempotency key
- object/provider identity
- declared byte size
- durable plaintext offset
- next multipart part
- retry count
- provider upload ID
- per-part ETag, size and SHA-256
- terminal/retryable state

A crash after a completed part can resume from the persisted plaintext offset.
Replaying an idempotency key for different transfer parameters fails closed.

## Segmented encryption

Large S3-compatible provider objects use
`vishnu-segmented-provider-object-v2`.

- A random 256-bit data key exists only in memory.
- The key is wrapped with the existing `EnvelopeKeyManager` / canonical vault.
- The remote header contains only wrapped key material and bounded metadata.
- Every plaintext segment is independently AES-256-GCM authenticated.
- Every segment carries a SHA-256 plaintext digest and sequence number.
- The concatenated provider object can be range-read and decrypted with bounded
  memory.
- An optional whole-source SHA-256 can be checked before multipart completion.

This avoids the previous single JSON envelope's bounded whole-object memory path
for large S3/R2/B2 objects while preserving the existing key authority.

## S3-compatible multipart/range path

The native multipart path supports the S3 APIs shared by Amazon S3,
Cloudflare R2 and Backblaze B2 S3 compatibility:

1. initiate multipart upload
2. upload bounded parts
3. persist each successful ETag/checkpoint
4. resume using the same upload ID
5. verify source size/digest
6. complete multipart upload
7. HEAD the completed object
8. only then record the durable provider location

Aborted or failed uploads do not become authorized durable locations.

Downloads use bounded `Range` requests and the segmented decoder rather than
loading the complete provider object into memory.

## Replica reconciliation

Recorded provider locations are verified with provider `HEAD`/metadata requests.

Outcomes include:

- `verified`
- `confirmed_missing`
- `provider_unreachable`
- `invalid_location_metadata`

A confirmed missing object is marked missing/unavailable. A provider outage only
marks availability false while retaining `has_bytes`, because an outage is not
proof that the remote object was deleted.

An unrecorded remote object is never silently adopted as an authorized replica.

## Tool surface

The added ToolRegistry surface is read-only:

- `data_storage_fabric_status`
- `data_storage_placement_preview`

No generic raw upload, arbitrary provider URL, credential, automatic repair, or
delete tool is added for an AI model.

## Security boundaries

- Provider credentials stay in `SecretVault` or existing canonical integration
  references.
- No automatic public sharing is created.
- No `anyone/writer` Drive permission is used.
- Custom S3 endpoints continue through the existing hardened provider adapter
  URL/network policy.
- Provider redirects remain blocked by existing adapters.
- Data policies are checked before provider upload jobs are created.
- `device_only` and `progress_only` cannot use provider byte upload jobs.
- `on_demand` never creates an automatic copy.
- Reconciliation cannot silently move data.

## Qualification

`tests/test_storage_fabric.py` covers:

- provider capability truthfulness
- policy-aware placement
- durable idempotent checkpoints
- checkpoint replay mismatch rejection
- interrupted multipart upload and resume
- bounded range download/decryption
- whole-source digest mismatch abort
- replica missing reconciliation
- health/status redaction boundaries

The test is included in the existing `Data Plane Qualification` workflow.

## External evidence boundary

Repository qualification proves Vishnu's software contracts using deterministic
provider fixtures. It does not fabricate live owner/provider evidence.

Before production claims for a provider, qualify the exact deployed build with
owner-approved sandbox/production credentials and the actual endpoint/account.
No production deployment or production credential is introduced by this work.
