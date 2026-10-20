# Platform parity — verified state

Status is deliberately conservative. A surface is not marked complete merely because it can open a PWA URL.

| Target | Entry/rendering | Screens 11–15 state | Qualification |
|---|---|---|---|
| Web app | `/web/campaign-demo` for isolated reference preview; `/web/` for the normal app | Five local-only reference previews (Home, Conversation, History, Voice, Search) with sample data; normal app screens are not replaced | Live browser check confirms app-server assets load; preview tests passed at desktop and 390px widths; not a pixel-diff pass |
| Windows desktop native | PyQt6 `CanonicalMainWindow` | Separate native UI; supplied five-screen OS shell not integrated | Unverified; no Windows native visual parity claim |
| macOS desktop native | Not established as a packaged target by this turn | No verified integrated Screens 11–15 entry | Unverified |
| Linux desktop native | PyQt6 source exists | PWA shell not integrated as the canonical native screen in this change | Unverified |
| Android app | Chrome Custom Tab handoff for full Vishnu experience | Not embedded native parity | Unverified on emulator/device for these screens |
| iOS app | Safari handoff for full Vishnu experience | Not embedded native parity | Unverified on simulator/device for these screens |
| iPad app | iOS companion source; adaptive layout not verified here | No campaign qualification | Unverified |

The local web runtime uses an isolated temporary SQLite data directory and starts with `first_run_status=uninitialized`; it is not using an external database. Owner authentication remains enabled on `/web/`; `/web/campaign-demo` is a read-only sample-data preview.

Native build toolchains/devices were not used in this slice. The demo route is web/PWA only; the desktop native UI and Android/iOS companion UI have not been integrated with these screens. This table is the gap statement, not a pass certificate. Full parity remains incomplete.
# Vishnu platform names and laptop quick start

Vishnu has three distinct ways to use the product:

- **Web app**: opens in a browser on any supported computer or phone.
- **Desktop app**: the installed/native Windows, macOS, or Linux application.
- **Mobile app**: the Android or iOS companion application.

The browser surface is called the **web app** throughout user-facing instructions. Its canonical local route is `/web/`.

On the current development laptop, the clean local web server for the shared development data is listening on port 8770:

- Sample-data Screens 11–15 web preview: `http://127.0.0.1:8770/web/campaign-demo`
- Normal local web app: `http://127.0.0.1:8770/web/` (uses this local instance's first-run/owner setup)

Start the web runtime with `powershell -ExecutionPolicy Bypass -File .\scripts\start_web_dev.ps1`, then complete first-run setup once. Start the Windows desktop from a second repository PowerShell terminal with `powershell -ExecutionPolicy Bypass -File .\scripts\start_windows_dev.ps1`. Both use the same isolated development data directory; the desktop **Open web app** action opens the web runtime, not its own API port. The native process still has its own in-memory runtime, so this shares on-disk development data—not full live runtime synchronization. Avoid using the regular `.local-data` directory for this workflow. The supplied Screens 11–15 design preview remains web-only and is not yet integrated into the native desktop or mobile shells.

## Screens 11–15 platform parity status
