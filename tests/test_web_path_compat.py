import asyncio
from pathlib import Path

from server.web_path_compat import CanonicalWebPathMiddleware


def run_asgi(app, scope):
    messages = []

    async def receive():
        return {'type': 'http.request', 'body': b'', 'more_body': False}

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    return messages


def test_web_alias_serves_existing_pwa_and_rewrites_visible_paths_and_length():
    seen = {}

    async def app(scope, receive, send):
        seen['path'] = scope['path']
        await send({'type': 'http.response.start', 'status': 200, 'headers': [
            (b'content-type', b'text/html; charset=utf-8'),
            (b'content-length', b'99'), (b'etag', b'old'),
        ]})
        await send({'type': 'http.response.body', 'body': b'<a href="/iphone/">Vishnu</a>'})

    messages = run_asgi(CanonicalWebPathMiddleware(app), {
        'type': 'http', 'method': 'GET', 'path': '/web/', 'raw_path': b'/web/',
        'query_string': b'', 'headers': [],
    })

    assert seen['path'] == '/iphone/'
    assert messages[-1]['body'] == b'<a href="/web/">Vishnu</a>'
    headers = dict(messages[0]['headers'])
    assert headers[b'content-length'] == str(len(messages[-1]['body'])).encode()
    assert b'etag' not in headers


def test_legacy_browser_url_redirects_to_platform_neutral_url_preserving_query():
    async def unexpected_app(scope, receive, send):
        raise AssertionError('legacy path should redirect before routing')

    messages = run_asgi(CanonicalWebPathMiddleware(unexpected_app), {
        'type': 'http', 'method': 'GET', 'path': '/iphone/campaign-demo',
        'raw_path': b'/iphone/campaign-demo', 'query_string': b'campaignDemo=1', 'headers': [],
    })

    assert messages[0]['status'] == 308
    assert dict(messages[0]['headers'])[b'location'] == b'/web/campaign-demo?campaignDemo=1'


def test_legacy_api_path_is_not_redirected_so_scoped_auth_cookies_are_sent():
    seen = {}

    async def app(scope, receive, send):
        seen['path'] = scope['path']
        await send({'type': 'http.response.start', 'status': 200, 'headers': [
            (b'content-type', b'application/json'),
            (b'set-cookie', b'vishnu-trust=token; Path=/iphone; HttpOnly'),
        ]})
        await send({'type': 'http.response.body', 'body': b'{"ok":true}'})

    messages = run_asgi(CanonicalWebPathMiddleware(app), {
        'type': 'http', 'method': 'POST', 'path': '/iphone/api/first-run/resume',
        'raw_path': b'/iphone/api/first-run/resume', 'query_string': b'', 'headers': [],
    })

    assert seen['path'] == '/iphone/api/first-run/resume'
    assert messages[0]['status'] == 200
    assert dict(messages[0]['headers'])[b'set-cookie'].endswith(b'Path=/iphone; HttpOnly')


def test_windows_desktop_dev_launcher_enables_loopback_first_run_without_hosted_secret():
    root = Path(__file__).resolve().parents[1]
    launcher = (root / 'scripts' / 'start_windows_dev.ps1').read_text(encoding='utf-8')

    assert "$env:CONTROL_SERVER_HOST = '127.0.0.1'" in launcher
    assert "$env:PERSONAL_AI_IPHONE_ALLOW_INSECURE = '1'" in launcher
    assert "$env:PERSONAL_AI_BOOTSTRAP_SECRET = ''" in launcher
    assert 'PERSONAL_AI_IPHONE_ENROLLMENT_CODE' in launcher
    assert "'vishnu-owner-fresh-20261023'" in launcher
    assert '[int]$WebPort = 8771' in launcher


def test_desktop_refuses_to_silently_reuse_a_local_server_with_first_run_disabled():
    root = Path(__file__).resolve().parents[1]
    desktop = (root / 'scripts' / 'run_local_desktop.py').read_text(encoding='utf-8')

    assert 'def _verify_existing_local_setup' in desktop
    assert '/web/api/access/options' in desktop
    assert 'no Vishnu data was changed' in desktop
    assert 'PersistentCookiesPolicy.ForcePersistentCookies' in desktop
    assert 'profile_dir = settings.data_dir / "browser-profile"' in desktop


def test_web_dev_launcher_uses_the_same_data_directory_and_port_as_windows_desktop():
    root = Path(__file__).resolve().parents[1]
    launcher = (root / 'scripts' / 'start_web_dev.ps1').read_text(encoding='utf-8')

    assert "'vishnu-owner-fresh-20261023'" in launcher
    assert '[int]$Port = 8771' in launcher
