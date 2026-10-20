# Local Vishnu development: Web + Windows

Use this workflow to run the browser app and native Windows app against one isolated development data directory. It does not connect to production and does not use the repository's existing `.local-data` directory.

## Start the web app

Open a PowerShell terminal in `E:\Vishnu` and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_web_dev.ps1
```

Keep this terminal open. Visit:

- Web app: <http://127.0.0.1:8770/web/>
- Screens 11–15 sample preview: <http://127.0.0.1:8770/web/campaign-demo>

The sample preview is for visual review and uses local fixture data. The normal web app uses the isolated local development runtime. On a fresh runtime, create your owner directly in the browser; this loopback-only launcher does not ask for a setup code. The visible Create flow is Welcome → Name → Secure Vishnu → Save Recovery Key. The current runtime requires an owner password; a passkey can be added when supported. Save the one-time recovery codes. This first owner is stored only in the isolated development data folder.

If the setup page asks for a **Local runtime setup code**, it is not being served with the local-development settings. Stop the web server currently using port 8770, then start it with the command above and reload `http://127.0.0.1:8770/web/`. The local loopback flow never needs a hosted runtime bootstrap code. Do not paste a production/hosted secret into local browser setup.

If setup was interrupted after the owner account was created, the welcome screen offers **Continue setup** and resumes from the last server-confirmed step. Do not choose account creation again. Recovery codes are shown only once; if setup resumes at recovery and you no longer have them, choose **Generate fresh recovery codes**, save the new set, then confirm and continue. Generating a fresh set invalidates the old codes.

The setup-only browser claim is renewed from the already enrolled first device when it expires, so a long pause does not require recreating the owner or resetting local data.

If the web app says this browser is not trusted or its saved sign-in credential is invalid, the browser's trusted-device session is missing or no longer valid. This does not mean the Vishnu account or its local data was deleted. Return to the welcome screen and choose **I already have Vishnu** to sign in with the owner method you configured. Do not choose **Create my Vishnu** again; that would attempt to create another owner instead of restoring this browser's access.

In the current web flow, **Restore Vishnu** with a recovery code restores owner access; it does not import a backup archive. Importing `.vdr` or `.paibackup` data is still available through the Windows app's first-run restore path. Web sign-in from an untrusted browser now creates a pending device-join request; approve it from an existing trusted web session under **Settings → Trusted Devices**. Approval currently requires the configured owner password, so passkey-only owners need another approved owner-verification path before using this join screen. Web/PWA backup-data restore and Windows login/join parity are still unfinished.

During maintenance restore, existing SQLite databases are updated through SQLite's online backup API instead of replacing their files. This avoids Windows file-sharing errors when a database handle is still open and allows SQLite to coordinate readers. Continuation authority is host-local: portable imports preserve the target ledger and reconstruct only the authenticated checkpoint/transfer grant; an already-initialized target is rejected before any restore writes.

## Start the Windows app

After the web app has started, open a second PowerShell terminal in `E:\Vishnu` and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_windows_dev.ps1
```

The native app opens in its own window. It shares the web app's isolated local data directory, and its **Open web app** action points to the local web address above. Its visible Create flow now uses the same three stages and applies local-only, device-only defaults after recovery is acknowledged. Complete first-run setup once, then refresh the other surface if it does not reflect a change immediately.

## What is and is not shared

Both programs use the same local files/database, but each currently constructs its own in-memory runtime. This is useful for iterative local development and persistent data checks; it does not guarantee instant synchronization of every in-memory preference, event, or active conversation. Screens 11–15 are currently a web preview and are not yet implemented in the native Windows screen set. Android and iOS entry screens have not yet been moved to the shortened flow, and native builds are not qualified by the checks below.

The development data directory defaults to `%TEMP%\vishnu-pixel-preview`. To use a different isolated folder, pass the same `-DataDirectory` value to both launchers. Do not point these launchers at `.local-data` or another owner-data directory.

Stop each app with `Ctrl+C` in its terminal or close the desktop window. Stopping does not remove development data. The `-ExecutionPolicy Bypass` option applies only to that PowerShell invocation; it does not change the machine's policy.

## Useful checks

From the repository root:

```powershell
node tests/campaign_demo_live_browser.mjs
python -m pytest tests/test_web_path_compat.py tests/test_genesis_native_ui_contract.py -q
```
