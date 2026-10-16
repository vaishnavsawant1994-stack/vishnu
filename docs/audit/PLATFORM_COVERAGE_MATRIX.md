# Platform Coverage Matrix

Baseline: `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

Values describe the feature scope evidenced by the repository, not universal production acceptance.

| Feature | Win desktop | macOS desktop | Linux desktop | Web desktop | Web mobile | Android phone/tablet | iPhone/iPad |
|---|---|---|---|---|---|---|---|
| Core conversation/shell | Complete | Complete | Complete | Complete | Partial | Partial | Partial |
| Memory/Knowledge access | Complete | Complete | Complete | Complete | Partial | Partial | Partial |
| Activities/Dashboard | Complete | Complete | Complete | Complete | Partial | Contextual | Contextual |
| Apps & Tools / OpenAPI/MCP management | Complete | Complete | Complete | Complete | Partial | Implemented; emulator-qualified | Implemented; simulator-qualified |
| First-device onboarding | Implemented | Implemented | Implemented | Implemented | Implemented | Partial/physical not verified | Partial/physical not verified |
| Trusted-device pairing | Complete | Complete | Complete | Complete | Complete | Emulator-qualified | Simulator-qualified |
| Work/Projects/Agents | Complete | Complete | Complete | Complete | Partial | Contextual | Contextual |
| Data-plane policy/control | Complete | Complete | Complete | Complete | Partial | Implemented | Implemented |
| Sensorium virtual/VM | Internal | Internal | Internal | Advanced | Advanced | Emulator scope | Simulator scope |
| Physical Sensorium/camera/sensors | N/A/device-dependent | N/A/device-dependent | N/A/device-dependent | Browser-dependent | Browser-dependent | Blocked/Not verified L4 | Blocked/Not verified L4 |
| Voice software runtime | Partial | Partial | Partial | Partial | Partial | Partial | Partial |
| Real telephony/acoustics | Blocked | Blocked | Blocked | Blocked | Blocked | Blocked | Blocked |
| Product development builds | Implemented | Implemented | Implemented | Implemented | N/A | Dev artifact implemented | Dev artifact implemented |
| Production signing/store acceptance | Blocked/external | Blocked/external | External distribution | N/A | N/A | Blocked/external | Blocked/external |
| Intelligence Lab | Experimental/Advanced | Experimental/Advanced | Experimental/Advanced | Experimental/Advanced | Unsupported by design/Advanced | N/A | N/A |

`Partial` on mobile often means the capability is available contextually through the trusted companion/runtime but the full desktop management surface is not proven at mobile parity. Emulator/simulator evidence is deliberately not rewritten as physical-device evidence.
