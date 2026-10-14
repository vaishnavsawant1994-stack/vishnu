from __future__ import annotations

import argparse
import difflib
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    'runtime': (ROOT / 'requirements.txt', ROOT / 'requirements.lock'),
    'tools': (ROOT / 'requirements-tools.in', ROOT / 'requirements-tools.lock'),
    'ml': (ROOT / 'requirements-ml.txt', ROOT / 'requirements-ml.lock'),
    'training': (ROOT / 'requirements-training.txt', ROOT / 'requirements-training.lock'),
}
BOOTSTRAP = (ROOT / 'requirements-bootstrap.in', ROOT / 'requirements-bootstrap.lock')
LOCK_FLAGS = (
    '--generate-hashes',
    '--universal',
    '--python-version',
    '3.11',
    '--no-header',
    '--quiet',
)
MAX_DIFF_LINES = 200


def _run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def _verify(source: Path, lock: Path) -> None:
    with tempfile.TemporaryDirectory(prefix='vishnu-lock-check-') as temporary:
        generated = Path(temporary) / lock.name
        _run(
            'uv', 'pip', 'compile', *LOCK_FLAGS,
            '--output-file', str(generated),
            str(source),
        )
        expected_text = lock.read_text()
        generated_text = generated.read_text()
        if generated_text != expected_text:
            diff = list(difflib.unified_diff(
                expected_text.splitlines(),
                generated_text.splitlines(),
                fromfile=lock.name,
                tofile=f'{lock.name}.generated',
                lineterm='',
            ))
            for line in diff[:MAX_DIFF_LINES]:
                print(line, file=sys.stderr)
            if len(diff) > MAX_DIFF_LINES:
                print(f'... lock diff truncated after {MAX_DIFF_LINES} lines', file=sys.stderr)
            raise SystemExit(f'{lock.name} is stale; regenerate it with uv 0.12.23.')


def main() -> int:
    parser = argparse.ArgumentParser(description='Verify and install a hash-locked Vishnu Python profile.')
    parser.add_argument('profile', choices=PROFILES, nargs='?', default='runtime')
    parser.add_argument('--check-only', action='store_true', help='verify freshness without installing project packages')
    parser.add_argument('--check-all', action='store_true', help='verify freshness of every Python dependency lock')
    args = parser.parse_args()
    source, lock = PROFILES[args.profile]

    _run(sys.executable, '-m', 'pip', 'install', '--require-hashes', '-r', str(BOOTSTRAP[1]))
    _verify(*BOOTSTRAP)
    profiles = PROFILES.values() if args.check_all else ((source, lock),)
    for profile_source, profile_lock in profiles:
        _verify(profile_source, profile_lock)

    if not args.check_only and not args.check_all:
        _run('uv', 'pip', 'install', '--system', '--require-hashes', '-r', str(lock))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
