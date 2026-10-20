import asyncio

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
