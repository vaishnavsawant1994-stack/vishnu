# Local Vishnu development: Web + Windows

Use this workflow to run Vishnu in Chrome and its Windows desktop window against one isolated local development data directory. The desktop embeds the same web application shown in Chrome, so both surfaces use the same layout and UI updates. It does not connect to production and does not use the repository's existing `.local-data` directory.

From the VS Code PowerShell terminal, use `npm.cmd run dev` to start the web runtime and `npm.cmd run desktop` to start the Windows desktop app. (`npm.ps1` may be blocked by the machine's PowerShell policy; `npm.cmd` avoids changing that policy.) Both use the same default isolated development folder. To select another folder, pass the same `-DataDirectory` argument to both npm scripts, for example `npm.cmd run dev -- -DataDirectory 'E:\Vishnu 2.0\dev-data'` and `npm.cmd run desktop -- -DataDirectory 'E:\Vishnu 2.0\dev-data'`. Start the web runtime first if you want Chrome and desktop open at the same time; the desktop reuses that local server.

## Start the web app

Open a PowerShell terminal in `E:\Vishnu 2.0` and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_web_dev.ps1
```

Keep this terminal open. Visit:

- Web app: <http://127.0.0.1:8771/web/>
- Screens 11â€“15 sample preview: <http://127.0.0.1:8771/web/campaign-demo>

The sample preview is for visual review and uses local fixture data. The normal web app uses the isolated local development runtime. On a fresh runtime, create your owner directly in the browser; this loopback-only launcher does not ask for a setup code. The visible Create flow is Welcome â†’ Name â†’ Secure Vishnu â†’ Save Recovery Key. The current runtime requires an owner password; a passkey can be added when supported. Save the one-time recovery codes. This first owner is stored only in the isolated development data folder.

If the setup page asks for a **Local runtime setup code**, it is not being served with the local-development settings. Stop the web server currently using port 8771, then start it with the command above and reload `http://127.0.0.1:8771/web/`. The local loopback flow never needs a hosted runtime bootstrap code. Do not paste a production/hosted secret into local browser setup.

If setup was interrupted after the owner account was created, the welcome screen resumes the final Phase 1 flow at the server-confirmed checkpoint. It does not create a duplicate owner. Recovery codes are shown only once; if setup resumes at recovery and you no longer have them, choose **Generate New Codes**, save the new set, then confirm and continue. Generating a fresh set invalidates the old codes.

The setup-only browser claim is renewed from the already enrolled first device when it expires, so a long pause does not require recreating the owner or resetting local data.

If the web app says this browser is not trusted or its saved sign-in credential is invalid, the browser's trusted-device session is missing or no longer valid. This does not mean the Vishnu account or its local data was deleted. Return to the welcome screen and choose **I already have Vishnu** to sign in with the owner method you configured. Do not choose **Create my Vishnu** again; that would attempt to create another owner instead of restoring this browser's access.

In the current Phase 1 flow, **Restore Vishnu** opens recovery options and verification. Recovery-code verification restores account access; it does not import a backup archive. Importing `.vdr` or `.paibackup` data remains a separate data-restore operation. Web sign-in from an untrusted browser creates a pending device-join request; approve it from an existing trusted web session under **Settings → Trusted Devices**. Approval currently requires the configured owner password, so passkey-only owners need another approved owner-verification path before using this join screen.

During maintenance restore, existing SQLite databases are updated through SQLite's online backup API instead of replacing their files. This avoids Windows file-sharing errors when a database handle is still open and allows SQLite to coordinate readers. Continuation authority is host-local: portable imports preserve the target ledger and reconstruct only the authenticated checkpoint/transfer grant; an already-initialized target is rejected before any restore writes.

## Start the Windows app

After the web app has started, open a second PowerShell terminal in `E:\Vishnu 2.0` and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_windows_dev.ps1
```

The desktop app opens a native window that hosts the same local web interface. If the web server is already running on the selected port, the desktop reuses it. Otherwise, the desktop starts the local web runtime itself. Complete first-run setup once; Chrome and the desktop then share the same runtime and data directory.

## What is and is not shared

Chrome and the embedded desktop window connect to the same local web runtime. Screens 11â€“15 remain a web preview and do not represent native Windows or mobile-specific layouts. Android and iOS entry screens have not yet been moved to the shortened flow, and mobile builds are not qualified by the checks below.

The development data directory defaults to `%TEMP%\vishnu-owner-fresh-20261023`. Both launchers use port 8771 and the same folder. The Windows app stores its trusted-browser cookies in that folder so the first-device setup can resume securely after an app restart. To use a different isolated folder, pass the same `-DataDirectory` value to both launchers. Do not point these launchers at `.local-data` or another owner-data directory.

Stop each app with `Ctrl+C` in its terminal or close the desktop window. Stopping does not remove development data. The `-ExecutionPolicy Bypass` option applies only to that PowerShell invocation; it does not change the machine's policy.

## Useful checks

From the repository root:

```powershell
node tests/campaign_demo_live_browser.mjs
python -m pytest tests/test_web_path_compat.py tests/test_genesis_native_ui_contract.py -q
```
