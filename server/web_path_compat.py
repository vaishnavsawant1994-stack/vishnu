"""Expose a platform-neutral browser URL while retaining legacy PWA routes."""

from __future__ import annotations

class CanonicalWebPathMiddleware:
    """Serve the existing browser surface under /web and rewrite old links.

    Existing clients may continue using the historical route internally. New
    browser links, redirects, HTML, scripts, and JSON point to /web instead.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return

        path = scope.get('path', '')
        if path == '/iphone' or path.startswith('/iphone/'):
            suffix = path[len('/iphone'):]
            if suffix == '':
                suffix = '/'
            query = scope.get('query_string', b'')
            location = b'/web' + suffix.encode('utf-8') + (b'?' + query if query else b'')
            await send({
                'type': 'http.response.start', 'status': 308,
                'headers': [(b'location', location), (b'content-length', b'0')],
            })
            await send({'type': 'http.response.body', 'body': b''})
            return
        if path == '/web':
            scope = dict(scope, path='/iphone/')
        elif path.startswith('/web/'):
            scope = dict(scope, path='/iphone' + path[len('/web'):])
        else:
            scope = dict(scope)
        if 'raw_path' in scope and (path == '/web' or path.startswith('/web/')):
            scope['raw_path'] = scope['path'].encode('utf-8')

        response_start = None
        response_body = bytearray()

        async def send_canonical(message):
            nonlocal response_start
            message_type = message['type']
            if message_type == 'http.response.start':
                headers = []
                for name, value in message.get('headers', []):
                    if name.lower() in {b'location', b'content-location', b'link'}:
                        value = value.replace(b'/iphone', b'/web')
                    headers.append((name, value))
                response_start = dict(message, headers=headers)
                content_type = next((value.split(b';', 1)[0].strip().lower()
                                     for name, value in headers
                                     if name.lower() == b'content-type'), b'')
                compressed = any(name.lower() == b'content-encoding' for name, _ in headers)
                rewrite_response = (
                    content_type.startswith(b'text/')
                    or content_type in {
                        b'application/json', b'application/manifest+json',
                        b'application/javascript', b'text/javascript',
                    }
                    or content_type.endswith(b'+json')
                    or content_type.endswith(b'javascript')
                ) and content_type != b'text/event-stream' and not compressed
                response_start['_canonical_web_rewrite'] = rewrite_response
                if not rewrite_response:
                    response_start = None
                    await send(dict(message, headers=headers))
                return

            if message_type == 'http.response.body' and response_start is None:
                await send(message)
                return

            if message_type == 'http.response.body' and response_start is not None:
                rewrite = response_start.pop('_canonical_web_rewrite', False)
                response_body.extend(message.get('body', b''))
                if message.get('more_body', False):
                    return
                body = bytes(response_body)
                if rewrite:
                    body = body.replace(b'/iphone', b'/web')
                    headers = [(name, value) for name, value in response_start['headers']
                               if name.lower() not in {b'content-length', b'etag'}]
                    headers.append((b'content-length', str(len(body)).encode('ascii')))
                    response_start['headers'] = headers
                await send(response_start)
                await send(dict(message, body=body, more_body=False))
                return

            await send(message)

        await self.app(scope, receive, send_canonical)
