from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .migrations import migrate_agent_continuity_schema
from .models import (
    AuthorityLease,
    AuthorityStatus,
    CheckpointStatus,
    ContinuityCheckpoint,
    TransferGrant,
    TransferGrantStatus,
)


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _token_hash(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _not_expired(value: str, *, now: datetime | None = None) -> bool:
    current = now or _now_dt()
    return datetime.fromisoformat(str(value)).astimezone(timezone.utc) > current


class ContinuityAuthorityError(PermissionError):
    pass


class ContinuityStore:
    """Durable single-slot continuation authority, checkpoints and transfer grants.

    Connections are intentionally short-lived so a validated cross-host restore can
    replace the database file before the target consumes a transfer grant.
    """

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._con() as connection:
            migrate_agent_continuity_schema(connection)

    def _con(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.path), timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _append_event_locked(
        connection: sqlite3.Connection,
        event_type: str,
        *,
        host_id: str | None = None,
        checkpoint_id: str | None = None,
        epoch: int | None = None,
        payload: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> None:
        connection.execute(
            """
            INSERT INTO continuity_events(
                event_type, host_id, checkpoint_id, epoch, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(event_type),
                host_id,
                checkpoint_id,
                epoch,
                _json(payload or {}),
                created_at or _iso(_now_dt()),
            ),
        )

    @staticmethod
    def _authority_row_locked(connection: sqlite3.Connection) -> sqlite3.Row | None:
        return connection.execute(
            "SELECT * FROM continuation_authority WHERE slot = 1"
        ).fetchone()

    @staticmethod
    def _assert_row_active(
        row: sqlite3.Row | None,
        *,
        host_id: str,
        epoch: int,
        token: str,
        now: datetime | None = None,
    ) -> None:
        if row is None:
            raise ContinuityAuthorityError("continuation authority is not initialized")
        if str(row["status"]) != AuthorityStatus.ACTIVE.value:
            raise ContinuityAuthorityError("continuation authority is fenced")
        if str(row["host_id"]) != str(host_id) or int(row["epoch"]) != int(epoch):
            raise ContinuityAuthorityError("continuation authority belongs to another host or epoch")
        expected = str(row["token_hash"] or "")
        if not expected or expected != _token_hash(token):
            raise ContinuityAuthorityError("continuation authority credential is invalid")
        if not _not_expired(str(row["expires_at"]), now=now):
            raise ContinuityAuthorityError("continuation authority lease expired")

    def current_authority(self) -> dict[str, Any] | None:
        with self._con() as connection:
            row = self._authority_row_locked(connection)
        return dict(row) if row is not None else None

    def bootstrap(
        self,
        *,
        host_id: str,
        token: str,
        ttl_seconds: int = 300,
    ) -> AuthorityLease:
        host = str(host_id or "").strip()
        if not host or not token:
            raise ValueError("host_id and authority token are required")
        if ttl_seconds < 30:
            raise ValueError("authority ttl must be at least 30 seconds")
        now_dt = _now_dt()
        now = _iso(now_dt)
        expires = _iso(now_dt + timedelta(seconds=int(ttl_seconds)))
        with self._con() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._authority_row_locked(connection)
            if row is None:
                epoch = 1
                connection.execute(
                    """
                    INSERT INTO continuation_authority(
                        slot, epoch, host_id, token_hash, checkpoint_id, status,
                        acquired_at, heartbeat_at, expires_at, fenced_at
                    ) VALUES (1, ?, ?, ?, NULL, ?, ?, ?, ?, NULL)
                    """,
                    (
                        epoch,
                        host,
                        _token_hash(token),
                        AuthorityStatus.ACTIVE.value,
                        now,
                        now,
                        expires,
                    ),
                )
                self._append_event_locked(
                    connection,
                    "authority.bootstrapped",
                    host_id=host,
                    epoch=epoch,
                    created_at=now,
                )
                connection.commit()
                return AuthorityLease(host, epoch, token, now, expires)

            # A restart of the same host may renew the same epoch with the same
            # host-derived credential. A different host, token, or fenced source
            # can never seize authority through bootstrap.
            self._assert_row_active(
                row,
                host_id=host,
                epoch=int(row["epoch"]),
                token=token,
                now=now_dt - timedelta(days=36500),  # validate identity/token; expiry is renewed below
            )
            connection.execute(
                "UPDATE continuation_authority SET heartbeat_at=?, expires_at=? WHERE slot=1",
                (now, expires),
            )
            self._append_event_locked(
                connection,
                "authority.renewed_after_restart",
                host_id=host,
                epoch=int(row["epoch"]),
                created_at=now,
            )
            connection.commit()
            return AuthorityLease(
                host,
                int(row["epoch"]),
                token,
                str(row["acquired_at"]),
                expires,
                row["checkpoint_id"],
            )

    def assert_active(self, *, host_id: str, epoch: int, token: str) -> AuthorityLease:
        with self._con() as connection:
            row = self._authority_row_locked(connection)
        self._assert_row_active(row, host_id=host_id, epoch=epoch, token=token)
        assert row is not None
        return AuthorityLease(
            host_id=str(row["host_id"]),
            epoch=int(row["epoch"]),
            token=token,
            acquired_at=str(row["acquired_at"]),
            expires_at=str(row["expires_at"]),
            checkpoint_id=row["checkpoint_id"],
        )

    def renew(
        self,
        *,
        host_id: str,
        epoch: int,
        token: str,
        ttl_seconds: int = 300,
    ) -> AuthorityLease:
        now_dt = _now_dt()
        now = _iso(now_dt)
        expires = _iso(now_dt + timedelta(seconds=max(30, int(ttl_seconds))))
        with self._con() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = self._authority_row_locked(connection)
            self._assert_row_active(row, host_id=host_id, epoch=epoch, token=token)
            connection.execute(
                "UPDATE continuation_authority SET heartbeat_at=?, expires_at=? WHERE slot=1",
                (now, expires),
            )
            connection.commit()
        assert row is not None
        return AuthorityLease(str(host_id), int(epoch), token, str(row["acquired_at"]), expires, row["checkpoint_id"])

    def record_checkpoint(self, checkpoint: ContinuityCheckpoint) -> ContinuityCheckpoint:
        payload = checkpoint.to_dict()
        now = _iso(_now_dt())
        with self._con() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT checkpoint_hash, payload_json FROM continuity_checkpoints WHERE id=?",
                (checkpoint.id,),
            ).fetchone()
            if existing is not None:
                if str(existing["checkpoint_hash"]) != checkpoint.checkpoint_hash:
                    raise ValueError("checkpoint id collision")
                connection.rollback()
                return ContinuityCheckpoint.from_dict(json.loads(existing["payload_json"]))
            connection.execute(
                """
                INSERT INTO continuity_checkpoints(
                    id, source_host_id, authority_epoch, checkpoint_hash,
                    payload_json, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint.id,
                    checkpoint.source_host_id,
                    checkpoint.authority_epoch,
                    checkpoint.checkpoint_hash,
                    _json(payload),
                    CheckpointStatus.CREATED.value,
                    checkpoint.created_at,
                    now,
                ),
            )
            self._append_event_locked(
                connection,
                "checkpoint.created",
                host_id=checkpoint.source_host_id,
                checkpoint_id=checkpoint.id,
                epoch=checkpoint.authority_epoch,
                payload={"checkpoint_hash": checkpoint.checkpoint_hash},
                created_at=now,
            )
            connection.commit()
        return checkpoint

    def get_checkpoint(self, checkpoint_id: str) -> tuple[ContinuityCheckpoint, str] | None:
        with self._con() as connection:
            row = connection.execute(
                "SELECT payload_json, status FROM continuity_checkpoints WHERE id=?",
                (str(checkpoint_id),),
            ).fetchone()
        if row is None:
            return None
        return ContinuityCheckpoint.from_dict(json.loads(row["payload_json"])), str(row["status"])

    def prepare_transfer_grant(self, grant: TransferGrant) -> TransferGrant:
        now = _iso(_now_dt())
        with self._con() as connection:
            connection.execute("BEGIN IMMEDIATE")
            checkpoint = connection.execute(
                "SELECT source_host_id, authority_epoch FROM continuity_checkpoints WHERE id=?",
                (grant.checkpoint_id,),
            ).fetchone()
            if checkpoint is None:
                raise KeyError(grant.checkpoint_id)
            if (
                str(checkpoint["source_host_id"]) != grant.source_host_id
                or int(checkpoint["authority_epoch"]) != grant.source_epoch
            ):
                raise ValueError("transfer grant does not match checkpoint authority")
            existing = connection.execute(
                "SELECT * FROM continuity_transfer_grants WHERE id=?",
                (grant.id,),
            ).fetchone()
            if existing is not None:
                if str(existing["token_hash"]) != grant.token_hash:
                    raise ValueError("transfer grant id collision")
                connection.rollback()
                return grant
            connection.execute(
                """
                INSERT INTO continuity_transfer_grants(
                    id, checkpoint_id, source_host_id, target_host_id, source_epoch,
                    token_hash, status, created_at, expires_at, consumed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                """,
                (
                    grant.id,
                    grant.checkpoint_id,
                    grant.source_host_id,
                    grant.target_host_id,
                    grant.source_epoch,
                    grant.token_hash,
                    TransferGrantStatus.PREPARED.value,
                    grant.created_at,
                    grant.expires_at,
                ),
            )
            self._append_event_locked(
                connection,
                "transfer.prepared",
                host_id=grant.source_host_id,
                checkpoint_id=grant.checkpoint_id,
                epoch=grant.source_epoch,
                payload={"grant_id": grant.id, "target_host_id": grant.target_host_id},
                created_at=now,
            )
            connection.commit()
        return grant

    def stage_import_authority(self, *, checkpoint: ContinuityCheckpoint) -> None:
        """Stage a verified foreign authority in a fresh target ledger.

        This replaces the unsafe practice of copying the source SQLite file over
        the target. A target with an existing authority must be explicitly
        decommissioned before import; we never overwrite it implicitly.
        """
        now = _iso(_now_dt())
        with self._con() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = self._authority_row_locked(connection)
            if existing is not None:
                raise ContinuityAuthorityError(
                    "target continuation authority already exists; stop and explicitly prepare this host for transfer"
                )
            connection.execute(
                """
                INSERT INTO continuation_authority(
                    slot, epoch, host_id, token_hash, checkpoint_id, status,
                    acquired_at, heartbeat_at, expires_at, fenced_at
                ) VALUES (1, ?, ?, NULL, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(checkpoint.authority_epoch),
                    str(checkpoint.source_host_id),
                    str(checkpoint.id),
                    AuthorityStatus.FENCED.value,
                    now,
                    now,
                    now,
                    now,
                ),
            )
            self._append_event_locked(
                connection,
                "authority.import_staged",
                host_id=checkpoint.source_host_id,
                checkpoint_id=checkpoint.id,
                epoch=checkpoint.authority_epoch,
                payload={"target_import": True},
                created_at=now,
            )
            connection.commit()

    def fence_for_transfer(
        self,
        *,
        grant_id: str,
        host_id: str,
        epoch: int,
        token: str,
    ) -> None:
        now_dt = _now_dt()
        now = _iso(now_dt)
        with self._con() as connection:
            connection.execute("BEGIN IMMEDIATE")
            authority = self._authority_row_locked(connection)
            self._assert_row_active(authority, host_id=host_id, epoch=epoch, token=token, now=now_dt)
            grant = connection.execute(
                "SELECT * FROM continuity_transfer_grants WHERE id=?",
                (str(grant_id),),
            ).fetchone()
            if grant is None:
                raise KeyError(grant_id)
            if str(grant["status"]) != TransferGrantStatus.PREPARED.value:
                raise ContinuityAuthorityError("transfer grant is not prepared")
            if (
                str(grant["source_host_id"]) != str(host_id)
                or int(grant["source_epoch"]) != int(epoch)
            ):
                raise ContinuityAuthorityError("transfer grant belongs to another authority")
            if not _not_expired(str(grant["expires_at"]), now=now_dt):
                connection.execute(
                    "UPDATE continuity_transfer_grants SET status=? WHERE id=?",
                    (TransferGrantStatus.EXPIRED.value, str(grant_id)),
                )
                connection.commit()
                raise ContinuityAuthorityError("transfer grant expired")
            connection.execute(
                """
                UPDATE continuation_authority
                SET status=?, token_hash=NULL, checkpoint_id=?, heartbeat_at=?,
                    expires_at=?, fenced_at=?
                WHERE slot=1
                """,
                (
                    AuthorityStatus.FENCED.value,
                    str(grant["checkpoint_id"]),
                    now,
                    now,
                    now,
                ),
            )
            connection.execute(
                "UPDATE continuity_checkpoints SET status=?, updated_at=? WHERE id=?",
                (CheckpointStatus.EXPORTED.value, now, str(grant["checkpoint_id"])),
            )
            self._append_event_locked(
                connection,
                "authority.fenced_for_transfer",
                host_id=host_id,
                checkpoint_id=str(grant["checkpoint_id"]),
                epoch=epoch,
                payload={"grant_id": str(grant_id), "target_host_id": str(grant["target_host_id"])},
                created_at=now,
            )
            connection.commit()

    def consume_transfer(
        self,
        *,
        grant_id: str,
        grant_token: str,
        target_host_id: str,
        target_authority_token: str,
        ttl_seconds: int = 300,
    ) -> AuthorityLease:
        if not grant_token or not target_authority_token:
            raise ValueError("grant and target authority credentials are required")
        now_dt = _now_dt()
        now = _iso(now_dt)
        expires = _iso(now_dt + timedelta(seconds=max(30, int(ttl_seconds))))
        with self._con() as connection:
            connection.execute("BEGIN IMMEDIATE")
            grant = connection.execute(
                "SELECT * FROM continuity_transfer_grants WHERE id=?",
                (str(grant_id),),
            ).fetchone()
            if grant is None:
                raise KeyError(grant_id)
            if str(grant["status"]) != TransferGrantStatus.PREPARED.value:
                raise ContinuityAuthorityError("transfer grant is not consumable")
            if str(grant["target_host_id"]) != str(target_host_id):
                raise ContinuityAuthorityError("transfer grant targets another host")
            if str(grant["token_hash"]) != _token_hash(grant_token):
                raise ContinuityAuthorityError("transfer grant credential is invalid")
            if not _not_expired(str(grant["expires_at"]), now=now_dt):
                connection.execute(
                    "UPDATE continuity_transfer_grants SET status=? WHERE id=?",
                    (TransferGrantStatus.EXPIRED.value, str(grant_id)),
                )
                connection.commit()
                raise ContinuityAuthorityError("transfer grant expired")

            authority = self._authority_row_locked(connection)
            if authority is None:
                raise ContinuityAuthorityError("source continuation authority is missing")
            if (
                str(authority["host_id"]) != str(grant["source_host_id"])
                or int(authority["epoch"]) != int(grant["source_epoch"])
            ):
                raise ContinuityAuthorityError("imported authority does not match transfer grant")
            next_epoch = int(grant["source_epoch"]) + 1
            checkpoint_id = str(grant["checkpoint_id"])
            connection.execute(
                """
                UPDATE continuation_authority
                SET epoch=?, host_id=?, token_hash=?, checkpoint_id=?, status=?,
                    acquired_at=?, heartbeat_at=?, expires_at=?, fenced_at=NULL
                WHERE slot=1
                """,
                (
                    next_epoch,
                    str(target_host_id),
                    _token_hash(target_authority_token),
                    checkpoint_id,
                    AuthorityStatus.ACTIVE.value,
                    now,
                    now,
                    expires,
                ),
            )
            connection.execute(
                "UPDATE continuity_transfer_grants SET status=?, consumed_at=? WHERE id=?",
                (TransferGrantStatus.CONSUMED.value, now, str(grant_id)),
            )
            connection.execute(
                "UPDATE continuity_checkpoints SET status=?, updated_at=? WHERE id=?",
                (CheckpointStatus.RESTORED.value, now, checkpoint_id),
            )
            self._append_event_locked(
                connection,
                "authority.transferred",
                host_id=str(target_host_id),
                checkpoint_id=checkpoint_id,
                epoch=next_epoch,
                payload={"grant_id": str(grant_id), "source_host_id": str(grant["source_host_id"])},
                created_at=now,
            )
            connection.commit()
        return AuthorityLease(str(target_host_id), next_epoch, target_authority_token, now, expires, checkpoint_id)

    def mark_checkpoint_verified(self, checkpoint_id: str, *, host_id: str, epoch: int) -> None:
        now = _iso(_now_dt())
        with self._con() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id FROM continuity_checkpoints WHERE id=?",
                (str(checkpoint_id),),
            ).fetchone()
            if row is None:
                raise KeyError(checkpoint_id)
            connection.execute(
                "UPDATE continuity_checkpoints SET status=?, updated_at=? WHERE id=?",
                (CheckpointStatus.VERIFIED.value, now, str(checkpoint_id)),
            )
            self._append_event_locked(
                connection,
                "checkpoint.verified",
                host_id=host_id,
                checkpoint_id=str(checkpoint_id),
                epoch=epoch,
                created_at=now,
            )
            connection.commit()

    def list_events(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._con() as connection:
            rows = connection.execute(
                """
                SELECT id, event_type, host_id, checkpoint_id, epoch, payload_json, created_at
                FROM continuity_events ORDER BY id DESC LIMIT ?
                """,
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        output: list[dict[str, Any]] = []
        for row in reversed(rows):
            output.append(
                {
                    "id": int(row["id"]),
                    "event_type": str(row["event_type"]),
                    "host_id": row["host_id"],
                    "checkpoint_id": row["checkpoint_id"],
                    "epoch": row["epoch"],
                    "payload": json.loads(row["payload_json"]),
                    "created_at": str(row["created_at"]),
                }
            )
        return output
