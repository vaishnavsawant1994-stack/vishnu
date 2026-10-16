# Platform coverage matrix

**Baseline SHA:** `a8d3310b4d9090a42800621b1b27cb6045443c1e`.

Legend: `Partial` means source and/or focused tests exist but the complete owner path is not proven; `Blocked` means external consent, signing, hardware, or provider qualification remains; `Internal` means the primary surface is owner/admin/agent infrastructure; `Not verified` means no executable evidence was gathered in this audit. No row implies universal production support.

| Feature | Windows desktop | macOS desktop | Linux desktop | Web desktop | Web mobile | Android phone/tablet | iPhone/iPad |
|---|---|---|---|---|---|---|---|
| First run / owner identity | Partial | Partial | Partial | Partial | Partial | Partial / runtime hosting setup | Partial / runtime hosting setup |
| Conversation/model routing | Partial | Partial | Partial | Partial | Partial | Partial companion | Partial companion |
| Memory | Partial | Partial | Partial | Partial | Partial | Not verified parity | Not verified parity |
| Knowledge/files | Partial | Partial | Partial | Partial | Partial | Partial / not all formats | Partial / not all formats |
| Device trust and management | Partial | Partial | Partial | Partial | Partial | Partial | Partial |
| OpenAPI/MCP capability management | Partial | Partial | Partial | Partial | Partial | Partial native Forge subset | Partial native Forge subset |
| Data-plane policy/fabric | Partial | Partial | Partial | Partial | Partial | Partial | Partial |
| Voice | Blocked by hardware/provider configuration | Blocked by hardware/provider configuration | Blocked by hardware/provider configuration | Partial / browser permission | Partial / browser permission | Partial; physical test blocked | Partial; physical test blocked |
| Sensorium | Internal/qualification | Internal/qualification | Internal/qualification | Partial owner controls | Partial owner controls | Partial; physical L4 blocked | Partial; physical L4 blocked |
| Projects/work/automation | Partial | Partial | Partial | Partial | Partial | Not verified parity | Not verified parity |
| Intelligence Lab | Internal/experimental | Internal/experimental | Internal/experimental | Internal/experimental | Internal/experimental | Internal/experimental | Internal/experimental |
| Voice Lab / telephony | Internal/experimental; provider blocked | Internal/experimental; provider blocked | Internal/experimental; provider blocked | Internal/experimental | Internal/experimental | Internal; real acoustics blocked | Internal; real acoustics blocked |
| Product build/distribution | Partial | Partial | Partial | Owner console | Owner console | Build target exists; signing blocked | Build target exists; signing blocked |

The `product_truth.json` file contains machine-readable per-feature platform status. Current Android emulator, iOS simulator, hosted VM, browser and packaging workflows are evidence for those exact environments and SHAs; they do not establish physical devices, signed public distribution or production acceptance.
