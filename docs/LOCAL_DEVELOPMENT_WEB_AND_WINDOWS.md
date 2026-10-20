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

The sample preview is for visual review and uses local fixture data. The normal web app uses the isolated local development runtime. On a fresh runtime, create your owner directly in the browser; this loopback-only launcher does not ask for a setup code. Choose a password or passkey, then save the one-time recovery codes. This first owner is stored only in the isolated development data folder.

## Start the Windows app

After the web app has started, open a second PowerShell terminal in `E:\Vishnu` and run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_windows_dev.ps1
```

The native app opens in its own window. It shares the web app's isolated local data directory, and its **Open web app** action points to the local web address above. Complete first-run setup once, then refresh the other surface if it does not reflect a change immediately.

## What is and is not shared

Both programs use the same local files/database, but each currently constructs its own in-memory runtime. This is useful for iterative local development and persistent data checks; it does not guarantee instant synchronization of every in-memory preference, event, or active conversation. Screens 11–15 are currently a web preview and are not yet implemented in the native Windows screen set.

The development data directory defaults to `%TEMP%\vishnu-pixel-preview`. To use a different isolated folder, pass the same `-DataDirectory` value to both launchers. Do not point these launchers at `.local-data` or another owner-data directory.

Stop each app with `Ctrl+C` in its terminal or close the desktop window. Stopping does not remove development data. The `-ExecutionPolicy Bypass` option applies only to that PowerShell invocation; it does not change the machine's policy.

## Useful checks

From the repository root:

```powershell
node tests/campaign_demo_live_browser.mjs
python -m pytest tests/test_web_path_compat.py tests/test_genesis_native_ui_contract.py -q
```
