from __future__ import annotations

from dataclasses import asdict

from tools.registry import Risk, Tool


def register(registry, fabric):
    """Register read-only storage-fabric inspection/planning tools.

    These tools never upload, download, reconcile, move, copy, delete, connect a
    provider, or change owner policy. Consequential storage mutations continue
    through the existing governed data-plane authorities.
    """
    existing = {tool.name for tool in registry.all()}

    def add(tool):
        if tool.name not in existing:
            registry.register(tool)
            existing.add(tool.name)

    add(
        Tool(
            'data_storage_fabric_status',
            'Inspect storage-fabric provider capabilities, replica health, durable transfer checkpoints, and optional item locations without revealing credentials.',
            lambda p: fabric.diagnostics(
                str(p['global_id']) if p.get('global_id') else None
            ),
            Risk.READ_ONLY,
            input_schema={
                'type': 'object',
                'properties': {
                    'global_id': {
                        'type': 'string',
                        'minLength': 1,
                        'maxLength': 240,
                    }
                },
                'additionalProperties': False,
            },
        )
    )

    def preview(parameters):
        decision = fabric.plan_placement(
            str(parameters['global_id']),
            list(parameters.get('candidates') or []),
            purpose=str(parameters.get('purpose') or 'explicit_copy'),
            explicit=bool(parameters.get('explicit', True)),
            required_bytes=int(parameters.get('required_bytes') or 0),
        )
        return asdict(decision)

    add(
        Tool(
            'data_storage_placement_preview',
            'Preview policy-compliant storage placement. This is advisory only and never moves or copies bytes.',
            preview,
            Risk.READ_ONLY,
            input_schema={
                'type': 'object',
                'required': ['global_id', 'candidates'],
                'properties': {
                    'global_id': {
                        'type': 'string',
                        'minLength': 1,
                        'maxLength': 240,
                    },
                    'purpose': {
                        'type': 'string',
                        'maxLength': 80,
                    },
                    'explicit': {'type': 'boolean'},
                    'required_bytes': {
                        'type': 'integer',
                        'minimum': 0,
                        'maximum': 687194767360,
                    },
                    'candidates': {
                        'type': 'array',
                        'maxItems': 64,
                        'items': {
                            'type': 'object',
                            'required': ['location_type', 'location_id'],
                            'properties': {
                                'location_type': {
                                    'type': 'string',
                                    'enum': ['device', 'provider'],
                                },
                                'location_id': {
                                    'type': 'string',
                                    'minLength': 1,
                                    'maxLength': 1024,
                                },
                                'provider_id': {
                                    'type': 'string',
                                    'maxLength': 100,
                                },
                                'healthy': {'type': 'boolean'},
                                'local': {'type': 'boolean'},
                                'latency_ms': {
                                    'type': 'number',
                                    'minimum': 0,
                                    'maximum': 600000,
                                },
                                'free_bytes': {
                                    'type': 'integer',
                                    'minimum': 0,
                                },
                                'cost_weight': {
                                    'type': 'number',
                                    'minimum': 0,
                                    'maximum': 20,
                                },
                                'adds_failure_domain': {'type': 'boolean'},
                            },
                            'additionalProperties': False,
                        },
                    },
                },
                'additionalProperties': False,
            },
        )
    )
