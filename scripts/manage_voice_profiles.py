from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from core.config import settings
from voice.conversion import VoiceConversionSettings, VoiceProfileError, VoiceProfileRegistry


def _registry() -> VoiceProfileRegistry:
    conversion = VoiceConversionSettings.from_settings(settings)
    return VoiceProfileRegistry(
        conversion.profile_store,
        max_reference_bytes=conversion.max_reference_bytes,
        max_reference_seconds=conversion.max_reference_seconds,
    )


def _local_wav(path_value: str) -> Path:
    raw = str(path_value or '').strip()
    if not raw or raw.startswith(('http://', 'https://', 'file://')):
        raise VoiceProfileError('reference audio must be an explicit local filesystem path')
    path = Path(raw).expanduser().resolve()
    if not path.is_file():
        raise VoiceProfileError('reference audio file does not exist')
    if path.suffix.lower() != '.wav':
        raise VoiceProfileError('reference audio must be a .wav file')
    return path


def _public(profile) -> dict:
    data = asdict(profile)
    data['active'] = profile.active
    return data


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description='Manage consent-gated local Vishnu voice profiles.',
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    enroll = subparsers.add_parser('enroll', help='Enroll a local WAV voice reference.')
    enroll.add_argument('--wav', required=True, help='Local WAV reference file. URLs are not accepted.')
    enroll.add_argument('--profile-id', required=True)
    enroll.add_argument('--display-name', required=True)
    enroll.add_argument('--purpose', required=True)
    enroll.add_argument(
        '--consent-attested',
        action='store_true',
        help='Confirm that the speaker explicitly consented to this enrollment and intended use.',
    )
    enroll.add_argument(
        '--canonical',
        action='store_true',
        help="Enroll the protected canonical Vishnu profile. Its profile id must be 'vishnu'.",
    )

    list_profiles = subparsers.add_parser('list', help='List enrolled profiles.')
    list_profiles.add_argument('--include-revoked', action='store_true')

    revoke = subparsers.add_parser('revoke', help='Revoke a voice profile.')
    revoke.add_argument('profile_id')
    revoke.add_argument(
        '--allow-canonical',
        action='store_true',
        help='Explicitly permit revoking the protected canonical Vishnu profile.',
    )

    delete = subparsers.add_parser('delete', help='Delete a voice profile and its local reference WAV.')
    delete.add_argument('profile_id')
    delete.add_argument(
        '--allow-canonical',
        action='store_true',
        help='Explicitly permit deleting the protected canonical Vishnu profile.',
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        registry = _registry()
        if args.command == 'enroll':
            wav_path = _local_wav(args.wav)
            profile = registry.enroll(
                wav_path.read_bytes(),
                profile_id=args.profile_id,
                display_name=args.display_name,
                purpose=args.purpose,
                consent_attested=args.consent_attested,
                canonical=args.canonical,
            )
            result = {'enrolled': True, 'profile': _public(profile)}
        elif args.command == 'list':
            result = {
                'profiles': [
                    _public(profile)
                    for profile in registry.list(include_revoked=args.include_revoked)
                ]
            }
        elif args.command == 'revoke':
            profile = registry.revoke(
                args.profile_id,
                allow_canonical=args.allow_canonical,
            )
            result = {'revoked': True, 'profile': _public(profile)}
        elif args.command == 'delete':
            registry.delete(
                args.profile_id,
                allow_canonical=args.allow_canonical,
            )
            result = {'deleted': True, 'profile_id': args.profile_id}
        else:  # pragma: no cover - argparse guarantees a valid command.
            parser.error('unsupported command')
            return 2
    except (OSError, VoiceProfileError) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}, sort_keys=True), file=sys.stderr)
        return 2

    print(json.dumps({'ok': True, **result}, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
