from __future__ import annotations

from tools.registry import Risk, Tool


def register(registry, data_plane):
    existing = {tool.name for tool in registry.all()}

    def add(tool):
        if tool.name not in existing:
            registry.register(tool)
            existing.add(tool.name)

    add(Tool(
        'data_location_inspect',
        'Inspect where a Vishnu data item is allowed to live and whether its source is currently reachable; params: global_id',
        lambda p: data_plane.item(str(p['global_id'])),
        Risk.READ_ONLY,
        input_schema={
            'type': 'object', 'required': ['global_id'],
            'properties': {'global_id': {'type': 'string', 'minLength': 1, 'maxLength': 240}},
            'additionalProperties': False,
        },
    ))

    add(Tool(
        'data_provider_inventory',
        'Inspect the owner storage mode and configured online-storage providers. This never reveals provider credentials.',
        lambda p: data_plane.diagnostics(),
        Risk.READ_ONLY,
        input_schema={'type': 'object', 'properties': {}, 'additionalProperties': False},
    ))

    def verify_lease(_parameters, result):
        try:
            observed = data_plane.validate_remote_lease(str(result['lease_id']), require_persist=False)
            return {
                'verified': observed['global_id'] == result['global_id'] and not observed['persist_allowed'],
                'reason': 'short-lived non-persistent data-plane lease read back',
                'evidence': {
                    'global_id': observed['global_id'], 'source_device_id': observed['source_device_id'],
                    'requester_device_id': observed['requester_device_id'], 'persist_allowed': observed['persist_allowed'],
                },
            }
        except Exception as exc:
            return {'verified': False, 'reason': type(exc).__name__, 'evidence': {}}

    add(Tool(
        'data_remote_access_prepare',
        'Prepare a short-lived trusted-device lease to view/use data on its source device. This does not copy or move data; params: global_id,requester_device_id,purpose',
        lambda p: data_plane.grant_remote_access(
            str(p['global_id']), requester_device_id=str(p['requester_device_id']),
            purpose=str(p.get('purpose') or 'view'), allow_persist=False,
            ttl_seconds=int(p.get('ttl_seconds') or 120),
        ),
        Risk.EXTERNAL_SIDE_EFFECT,
        verifier=verify_lease,
        verification_required=True,
        verification_method='short-lived data-plane lease bound to active trusted devices',
        input_schema={
            'type': 'object', 'required': ['global_id', 'requester_device_id'],
            'properties': {
                'global_id': {'type': 'string', 'minLength': 1, 'maxLength': 240},
                'requester_device_id': {'type': 'string', 'minLength': 1, 'maxLength': 200},
                'purpose': {'type': 'string', 'maxLength': 120},
                'ttl_seconds': {'type': 'integer', 'minimum': 1, 'maximum': 300},
            },
            'additionalProperties': False,
        },
    ))

    def verify_policy(parameters, result):
        try:
            observed = data_plane.item(str(parameters['global_id']))
            expected = str(parameters['policy'])
            return {
                'verified': observed['storage_policy'] == expected and result['storage_policy'] == expected,
                'reason': 'storage policy read back from canonical data-plane store',
                'evidence': {'global_id': observed['global_id'], 'storage_policy': observed['storage_policy'], 'version': observed['version']},
            }
        except Exception as exc:
            return {'verified': False, 'reason': type(exc).__name__, 'evidence': {}}

    add(Tool(
        'data_storage_policy_set',
        'Change where a Vishnu item may be persisted. On-demand syncs references/metadata and materializes bytes only through a separately authorized transfer. This is owner-authority work; params: global_id,policy,copy_allowed,remote_access_allowed',
        lambda p: data_plane.set_policy(
            str(p['global_id']), str(p['policy']), copy_allowed=p.get('copy_allowed'),
            remote_access_allowed=p.get('remote_access_allowed'),
        ),
        Risk.CRITICAL,
        verifier=verify_policy,
        requires_reauth=True,
        verification_required=True,
        verification_method='read-back from canonical data-plane policy store',
        input_schema={
            'type': 'object', 'required': ['global_id', 'policy'],
            'properties': {
                'global_id': {'type': 'string', 'minLength': 1, 'maxLength': 240},
                'policy': {'type': 'string', 'enum': ['device_only', 'sync_everywhere', 'progress_only', 'on_demand']},
                'copy_allowed': {'type': 'boolean'}, 'remote_access_allowed': {'type': 'boolean'},
            },
            'additionalProperties': False,
        },
    ))

    transport = getattr(data_plane, 'byte_transport', None)
    envelopes = getattr(data_plane, 'envelopes', None)
    if transport is None or envelopes is None:
        return

    def verify_transfer(_parameters, result):
        try:
            observed = transport.status(str(result['session_id']))
            return {
                'verified': observed['state'] == 'open' and observed['cache_policy'] == 'no_store' and not observed['raw_session_key_exposed'],
                'reason': 'lease-bound encrypted transfer session read back',
                'evidence': {
                    'session_id': observed['session_id'], 'global_id': observed['global_id'],
                    'source_device_id': observed['source_device_id'], 'requester_device_id': observed['requester_device_id'],
                    'cache_policy': observed['cache_policy'],
                },
            }
        except Exception as exc:
            return {'verified': False, 'reason': type(exc).__name__, 'evidence': {}}

    add(Tool(
        'data_secure_transfer_prepare',
        'Create an encrypted, no-store, lease-bound byte-transfer session for remote viewing. It never grants permanent copy authority.',
        lambda p: transport.open_transfer(
            str(p['global_id']), requester_device_id=str(p['requester_device_id']),
            expected_size=p.get('expected_size'), expected_digest=p.get('expected_digest'),
            chunk_size=int(p.get('chunk_size') or 65536), ttl_seconds=int(p.get('ttl_seconds') or 120),
        ),
        Risk.EXTERNAL_SIDE_EFFECT,
        verifier=verify_transfer,
        verification_required=True,
        verification_method='secure transfer session + canonical remote lease read-back',
        input_schema={
            'type': 'object', 'required': ['global_id', 'requester_device_id'],
            'properties': {
                'global_id': {'type': 'string', 'minLength': 1, 'maxLength': 240},
                'requester_device_id': {'type': 'string', 'minLength': 1, 'maxLength': 200},
                'expected_size': {'type': 'integer', 'minimum': 0, 'maximum': 8589934592},
                'expected_digest': {'type': 'string', 'minLength': 64, 'maxLength': 64},
                'chunk_size': {'type': 'integer', 'minimum': 1024, 'maximum': 262144},
                'ttl_seconds': {'type': 'integer', 'minimum': 1, 'maximum': 300},
            },
            'additionalProperties': False,
        },
    ))

    add(Tool(
        'data_encryption_status',
        'Inspect data-envelope/key-epoch status without exposing any keys.',
        lambda p: envelopes.diagnostics(),
        Risk.READ_ONLY,
        input_schema={'type': 'object', 'properties': {}, 'additionalProperties': False},
    ))

    def verify_epoch(_parameters, result):
        try:
            observed = envelopes.diagnostics()
            epoch = int(result['active_key_epoch'])
            active = [item for item in observed['epochs'] if item['epoch'] == epoch and item['active']]
            return {
                'verified': bool(active) and not observed['raw_keys_in_database'],
                'reason': 'new envelope key epoch read back without raw key exposure',
                'evidence': {'active_key_epoch': epoch, 'raw_keys_in_database': observed['raw_keys_in_database']},
            }
        except Exception as exc:
            return {'verified': False, 'reason': type(exc).__name__, 'evidence': {}}

    add(Tool(
        'data_encryption_key_rotate',
        'Rotate the data-envelope KEK epoch for future objects. Old epochs remain decryptable through the canonical vault.',
        lambda p: {'active_key_epoch': envelopes.rotate_epoch()},
        Risk.CRITICAL,
        verifier=verify_epoch,
        requires_reauth=True,
        verification_required=True,
        verification_method='vault-backed envelope epoch read-back',
        input_schema={'type': 'object', 'properties': {}, 'additionalProperties': False},
    ))
