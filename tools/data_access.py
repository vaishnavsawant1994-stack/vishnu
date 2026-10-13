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
            'type': 'object',
            'required': ['global_id'],
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
                    'global_id': observed['global_id'],
                    'source_device_id': observed['source_device_id'],
                    'requester_device_id': observed['requester_device_id'],
                    'persist_allowed': observed['persist_allowed'],
                },
            }
        except Exception as exc:
            return {'verified': False, 'reason': type(exc).__name__, 'evidence': {}}

    add(Tool(
        'data_remote_access_prepare',
        'Prepare a short-lived trusted-device lease to view/use data on its source device. This does not copy or move data; params: global_id,requester_device_id,purpose',
        lambda p: data_plane.grant_remote_access(
            str(p['global_id']),
            requester_device_id=str(p['requester_device_id']),
            purpose=str(p.get('purpose') or 'view'),
            allow_persist=False,
            ttl_seconds=int(p.get('ttl_seconds') or 120),
        ),
        Risk.EXTERNAL_SIDE_EFFECT,
        verifier=verify_lease,
        verification_required=True,
        verification_method='short-lived data-plane lease bound to active trusted devices',
        input_schema={
            'type': 'object',
            'required': ['global_id', 'requester_device_id'],
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
                'evidence': {
                    'global_id': observed['global_id'],
                    'storage_policy': observed['storage_policy'],
                    'version': observed['version'],
                },
            }
        except Exception as exc:
            return {'verified': False, 'reason': type(exc).__name__, 'evidence': {}}

    add(Tool(
        'data_storage_policy_set',
        'Change where a Vishnu item may be persisted. This is owner-authority work; params: global_id,policy,copy_allowed,remote_access_allowed',
        lambda p: data_plane.set_policy(
            str(p['global_id']),
            str(p['policy']),
            copy_allowed=p.get('copy_allowed'),
            remote_access_allowed=p.get('remote_access_allowed'),
        ),
        Risk.CRITICAL,
        verifier=verify_policy,
        requires_reauth=True,
        verification_required=True,
        verification_method='read-back from canonical data-plane policy store',
        input_schema={
            'type': 'object',
            'required': ['global_id', 'policy'],
            'properties': {
                'global_id': {'type': 'string', 'minLength': 1, 'maxLength': 240},
                'policy': {'type': 'string', 'enum': ['device_only', 'sync_everywhere', 'progress_only']},
                'copy_allowed': {'type': 'boolean'},
                'remote_access_allowed': {'type': 'boolean'},
            },
            'additionalProperties': False,
        },
    ))
