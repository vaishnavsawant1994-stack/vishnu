# VoiceStudio external provider

Vishnu can use VoiceStudio as an optional external speech provider without replacing or disturbing the existing Voice Intelligence, Voice Runtime, full-duplex voice, OpenVoice conversion, Sensorium, ToolRegistry, ApprovalManager, DeviceRegistry/DeviceGateway, SecretVault, Memory, Knowledge, or audit authorities.

## Boundary

VoiceStudio remains a separately installed and separately running service. Vishnu does not vendor VoiceStudio source code, Electron UI code, Python backend code, model weights, or transitive model dependencies.

The adapter in `voice/voicestudio.py` uses VoiceStudio's published OpenAI-compatible speech API on its normal backend service (port 3900 by default):

- `GET /.well-known/voicestudio-speech` for discovery/health
- `POST /v1/audio/speech` for text-to-speech
- `POST /v1/audio/transcriptions` for speech-to-text
- `POST /v1/audio/translations` for speech-to-English translation
- `GET /v1/models` for model discovery
- `GET /v1/audio/voices` for available voices
- `/mcp/` for richer VoiceStudio tools through Vishnu Universal Capabilities

The provider implements Vishnu's existing `TextToSpeechProvider` and `SpeechToTextProvider` contracts. It does not create a second router, scheduler, voice-profile database, approval system, credential store, device registry, or MCP execution authority.

## Safe activation

The integration is disabled by default:

```text
VISHNU_VOICESTUDIO_ENABLED=false
VISHNU_VOICESTUDIO_URL=http://127.0.0.1:3900
VISHNU_VOICESTUDIO_TTS_MODEL=tts-1
VISHNU_VOICESTUDIO_TTS_VOICE=alloy
VISHNU_VOICESTUDIO_STT_MODEL=whisper-1
VISHNU_VOICESTUDIO_TIMEOUT_SECONDS=30
VISHNU_VOICESTUDIO_MAX_TEXT_CHARS=20000
VISHNU_VOICESTUDIO_MAX_INPUT_AUDIO_BYTES=33554432
VISHNU_VOICESTUDIO_MAX_OUTPUT_AUDIO_BYTES=67108864
VISHNU_VOICESTUDIO_ALLOW_REMOTE=false
VISHNU_VOICESTUDIO_REQUIRE_HTTPS_REMOTE=true
```

When `VISHNU_VOICESTUDIO_ENABLED=false`, application composition does not parse or validate any other VoiceStudio setting and allocates no VoiceStudio provider or provider runtime. This keeps stale optional configuration from disturbing the existing startup path. The Universal Capabilities bootstrap follows the same disabled-configuration rule.

When `VISHNU_VOICESTUDIO_ENABLED=true`, `app/main.py` composes one VoiceStudio provider behind the existing bounded `VoiceRuntime`. The provider is registered for both STT and TTS, the bounded runtime starts only after normal first-run setup succeeds, remains available for the Vishnu application lifetime, and stops through the existing application shutdown path. The current `RealtimeVoiceSession` remains separate and unchanged.

Credentials are intentionally not loaded by `VoiceStudioSettings`. For a remote endpoint, application composition reads only `voicestudio.api_key` from the already-authenticated canonical Vishnu `SecretVault` and injects it into `VoiceStudioProvider(api_key=...)`. Remote endpoints fail closed unless remote use is explicitly enabled; HTTPS is required by default and an injected bearer key is mandatory.

Loopback use can remain credential-free when the separately running VoiceStudio deployment is configured that way.

## Continuous operation

VoiceStudio is a stateless inference provider behind Vishnu's existing runtime, not a second orchestrator. Each inference call is bounded and independently authenticated. Once explicitly enabled, Vishnu keeps the provider runtime alive for the app session rather than repeatedly creating and destroying it.

Vishnu does not make successful VoiceStudio health probing a startup dependency. If the separately running VoiceStudio service is stopped, unhealthy, or unreachable, the adapter reports provider failure when used; the rest of Vishnu remains available and the current realtime voice flow is not silently replaced.

Vishnu does not auto-download VoiceStudio, model weights, or speech engines and does not silently launch a third-party process. The separately installed VoiceStudio service and exact model engines must be provisioned and qualified for the target deployment.

## Governed MCP capabilities

When VoiceStudio is enabled, Vishnu registers its configured `/mcp/` endpoint as inert metadata in the existing durable Universal Capabilities catalog. Startup does **not** contact the MCP service, discover tools, copy a provider credential, create a connection, approve a tool, or grant execution authority.

The owner must explicitly connect/discover the registered VoiceStudio server through the existing Capability Console/API. Only then does Vishnu contact `/mcp/`, import bounded tool schemas, and create the server connection. Each discovered tool remains non-executable until the owner reviews and approves its risk classification through the same Universal Capabilities flow used by other MCP tools.

For the normal local deployment, only the internally configured VoiceStudio server descriptor can carry the dedicated trusted-loopback marker. User-added MCP servers still pass through `normalize_mcp_server` plus the existing public-address HTTPS validation and therefore cannot opt themselves into loopback transport.

The dedicated loopback transport accepts only IP-literal loopback origins, ignores proxy environment variables, binds calls to the approved origin and MCP path, blocks redirects, caps timeouts, and applies the existing MCP response-size limit. The normal public MCP and OpenAPI transports remain unchanged.

VoiceStudio-specific minimum risks are persisted with discovered tool metadata and enforced server-side:

- listing, status, health, describe and inspection-style operations may be `read`
- voice cloning, voice design, transcription, speech/media generation, dubbing, unknown future operations and other non-discovery operations are at least `write`
- delete, remove, revoke, drop, purge, reset and disable-style operations are `destructive`

An owner may classify a tool more strictly than this minimum, but never less strictly. The approval endpoint rejects a weaker classification, and governed tool attachment independently checks the minimum again so process-restart rehydration cannot reactivate an under-classified tool.

Read-classified tools use the existing read path. Write/destructive tools continue through Vishnu's exact one-use owner approval and durable execution path. Disconnecting the MCP server revokes its discovered tools and blocks later execution through the live catalog connection fence.

For remote VoiceStudio deployments, the registered MCP URL remains HTTPS-only. MCP authentication is established only during the explicit owner connection flow and stored under the existing encrypted MCP credential lifecycle; startup registration does not copy or expose the core VoiceStudio provider key.

## Security controls

The integration:

- is disabled by default
- allows bounded loopback speech endpoints by default
- leaves optional VoiceStudio settings inert while disabled
- requires explicit opt-in for remote hosts
- requires HTTPS for remote hosts by default
- requires an injected bearer credential for enabled remote speech use
- keeps secrets in the existing Vishnu `SecretVault`
- rejects credentials embedded in endpoint URLs
- blocks HTTP redirects
- applies request timeouts and response-size caps
- returns sanitized transport errors and does not put bearer keys in capabilities or normal status output
- requests WAV output and validates the returned WAV before accepting it
- wraps raw 16-bit mono PCM into WAV for the batch transcription API
- keeps public MCP discovery HTTPS/public-address constrained
- registers VoiceStudio MCP metadata without contacting or authorizing the service at startup
- requires recent owner authentication to connect/discover and classify MCP tools
- enforces provider minimum risks in both approval and attachment paths
- grants no MCP tool execution merely because VoiceStudio is configured or discovered

## Voice cloning, design, dubbing, and other VoiceStudio tools

Higher-level VoiceStudio operations enter through Vishnu Universal Capabilities and the existing owner approval system. Vishnu's governed `VoiceProfileRegistry` remains the authoritative in-process enrollment/consent source for the native OpenVoice conversion path; the VoiceStudio MCP integration does not create a second Vishnu cloning database.

Possession or discovery of a VoiceStudio MCP tool is not consent to clone a person's voice. Operators remain responsible for obtaining the required consent for reference audio and complying with applicable law/provider terms before approving a cloning operation.

## Licensing

VoiceStudio is currently distributed under GNU AGPL v3. Vishnu is proprietary, so this integration deliberately does not copy, vendor, link, or modify VoiceStudio source code in this repository. It communicates with a separately installed service through VoiceStudio's documented network interfaces.

VoiceStudio upstream also publishes a separate commercial-license option for closed-source/proprietary embedding. This integration does not assume that such a license has been obtained. Distribution, hosted-service obligations, commercial licensing, model/checkpoint licenses, and transitive dependencies must be reviewed for the exact deployment before production distribution.

That boundary is an engineering safeguard, not legal advice.

## Qualification boundary

Repository tests qualify adapter contracts, isolation, endpoint construction, size bounds, loopback/remote policy, bearer injection, PCM-to-WAV wrapping, TTS result validation, disabled-configuration inertness, app-lifetime runtime composition, inert MCP registration, trusted-loopback isolation, origin/path binding, redirect and response-size blocking, durable tool metadata, provider risk floors, and fail-soft registration without installing VoiceStudio or model weights.

Production claims still require qualification against the exact VoiceStudio revision, exact enabled TTS/STT/MCP engines and model checkpoints, target CPU/GPU hardware, remote network/TLS configuration when applicable, real microphone/audio devices, and the deployment's licensing terms. No production deployment is performed by this repository change.