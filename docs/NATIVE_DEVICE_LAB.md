# Vishnu Native Device Lab

Vishnu uses three distinct device-validation layers. They must not be conflated.

## Layer 1 — Vishnu Virtual Device Fleet

The Sensorium virtual fleet is Vishnu's deterministic hardware-free simulation layer. It models Android, iOS, Windows, macOS, and Linux device state, permissions, sensors, failures, reconnects, and recovery scenarios without booting a vendor operating system.

## Layer 2 — Native Emulator, Simulator, and Desktop VM Qualification

The Native Device Lab validates Vishnu against real vendor/native runtime environments while physical hardware is unavailable.

### Android Emulator

The existing Android instrumentation workflow boots Google's Android Emulator and runs the companion instrumentation suite. `AndroidEmulatorProbe` then collects bounded read-only evidence through fixed `adb` queries.

The probe:

- accepts only active `emulator-*` targets;
- verifies QEMU/emulator identity;
- rejects physical ADB serials;
- reads only bounded device/version/ABI/boot/battery information;
- exposes no generic ADB, shell, install, push, input, URL, app-launch, or package-control API.

### iOS Simulator

The existing iOS companion workflow uses Apple's CoreSimulator and `xcodebuild` with simulator destinations. `IOSSimulatorProbe` reads the available CoreSimulator inventory with a fixed `simctl list ... --json` command and records the selected simulator's runtime/state metadata.

The server exposes no arbitrary `simctl` or shell endpoint.

### Desktop hosted VM qualification

The Native Device Lab workflow runs on GitHub-hosted Ubuntu, Windows, and macOS qualification runners. `DesktopVMProbe` accepts only GitHub Actions hosted-runner context or an explicitly declared `VISHNU_DESKTOP_VM` environment. It records OS/runtime evidence with `physical_device=false` and `execution_authority=false`.

This is qualification of hosted/declarative desktop virtual environments. It is not a claim that every hypervisor or every physical PC/Mac has been tested.

## Evidence model

Native evidence is stored in `NativeDeviceLab` and can be inspected through the authenticated Sensorium native evidence API. Evidence includes provider, platform, target identifier, runtime version, architecture, bounded capabilities, safe metadata, timestamp, and source.

The evidence model rejects:

- secret-bearing metadata keys;
- `physical_device=true` claims;
- `execution_authority=true` claims;
- invalid provider/platform combinations.

Shared EventBus and Live Work projections contain metadata only. Raw command output and evidence metadata are not projected into shared listeners.

## Authority boundary

Native Device Lab is an observation and qualification system only. It does not replace or bypass Vishnu's existing Computer Control, ToolRegistry, ApprovalManager, emergency stop, verification, audit, cancellation, or durable recovery systems.

Physical side effects remain under those existing governed authorities.

## Layer 3 — Physical devices

Real Android phones/tablets, iPhones/iPads, Windows/macOS/Linux machines, cameras, microphones, Bluetooth/NFC peripherals, and other physical hardware are a later qualification layer. Native-emulator and hosted-VM success must never be reported as real-hardware qualification.
