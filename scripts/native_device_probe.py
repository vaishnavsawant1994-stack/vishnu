from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sensorium.native_lab import AndroidEmulatorProbe, DesktopVMProbe, IOSSimulatorProbe


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect bounded, read-only Vishnu native-device qualification evidence")
    parser.add_argument("provider", choices=("android", "ios", "desktop"))
    parser.add_argument("--serial", default=None)
    parser.add_argument("--udid", default=None)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.provider == "android":
        evidence = AndroidEmulatorProbe().probe(args.serial)
    elif args.provider == "ios":
        evidence = IOSSimulatorProbe().probe(args.udid)
    else:
        evidence = DesktopVMProbe().probe()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
