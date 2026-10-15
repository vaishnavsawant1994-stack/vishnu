# Vishnu Intelligence Lab Phase 3.1 — Governed Trusted-Device Compute

Phase 3 added trusted-device placement and hardware acceleration advice but
intentionally did not dispatch remote work. Phase 3.1 closes that execution gap
without giving the Intelligence Lab a new execution authority.

## Execution boundary

```text
Lab placement
   |
   v
Lab ActionProposal: trusted_device_compute
   |
   v
VishnuCoreBridge
   |
   v
existing AgentExecutor re-plans
   |
   v
existing ToolRegistry + owner permission/approval + emergency stop
   |
   v
trusted_device_compute Core tool
   |
   v
existing DeviceGateway
   |
   v
separately enrolled trusted compute worker
   |
   v
verified response -> Core audit/result
```

The Lab never calls `DeviceGateway` directly.

## Live device capability

A compute worker must be a separately paired/trusted device and advertise:

`intelligence_compute_v1`

through the existing `/device/ws/{device_id}` channel. `DeviceGateway` keeps the
advertisement in memory only for the live session. Capability advertisement is
not permission.

The target must also have the existing owner-grade `device:admin` permission.
The registered tool is `EXTERNAL_SIDE_EFFECT`, requires result verification and
normal Core approval semantics, and prohibits secret/sensitive/restricted data.

## Protocol

The command action is `intelligence_compute_v1` and the protocol identifier is:

`vishnu.trusted-compute/v1`

Inputs are bounded to:

- prompt: <= 12,000 characters;
- context: bounded JSON <= 64 KiB and bounded depth/items;
- mode: `fast`, `smart`, or `deep`;
- sensitivity: `public` or `internal` only;
- max tokens: 1..8192;
- timeout: 1..120 seconds;
- destination must exactly bind to `device:<device_id>`.

There is no shell/code field, arbitrary tool field, credential field, file
execution field or security-policy field.

## Worker

`devices.trusted_compute.TrustedComputeWorker` receives only the bounded request
and calls an injected reasoner callback. It does not own or retrieve provider
credentials. A remote Vishnu runtime can inject its existing governed model
router/intelligence callback.

`TrustedComputeWebSocketWorker` supplies the secure WSS command transport for a
separately enrolled compute device. It refuses HTTP/WS transport.

## Gateway bridge

`DeviceGateway.request_sync()` schedules the request onto the device's existing
asyncio WebSocket loop using `run_coroutine_threadsafe`. It explicitly refuses
to block the device loop itself. This lets synchronous ToolRegistry execution
use the already-authenticated async device channel without creating a second
transport.

## Lab behavior

`phase3.distributed_compute_proposal(...)` selects only online devices that:

1. are active/trusted;
2. have `device:admin`;
3. advertise `intelligence_compute_v1` in the current session;
4. are eligible for public/internal remote work.

It creates an ActionProposal and performs no dispatch.

`phase3.execute_distributed_compute(...)` is in-process only and returns the
proposal to `VishnuCoreBridge.execute()`. The bridge sends untrusted advisory
data to the normal AgentExecutor, which re-plans and applies existing Core
policy/approval/verification. The standalone Phase-3 HTTP service deliberately
exposes no remote-compute execution endpoint.

## Default behavior

`app/main.py` still does not import or attach the Intelligence Lab. The compute
tool is registered into the existing ToolRegistry only when an explicitly
enabled Lab is built with the canonical Core ToolRegistry, DeviceRegistry and
DeviceGateway attached.

With the Lab disabled, normal Vishnu behavior is unchanged.

## Qualification

The Phase 3.1 tests cover:

- opt-in-only Core tool registration;
- existing `device:admin` requirement;
- live capability requirement;
- bounded prompt/context and destination binding;
- secret/sensitive/restricted remote-compute prohibition;
- verified device/request/protocol response binding;
- injected-reasoner worker behavior and no arbitrary action;
- proposal-only path performs no gateway dispatch;
- governed execution returns to AgentExecutor instead of bypassing Core;
- standalone service still has no `/execute` or tool-dispatch endpoint.

Phase 3.1 is distributed-compute infrastructure. It is not evidence of AGI,
ASI, consciousness or autonomous authority outside Vishnu Core policy.
