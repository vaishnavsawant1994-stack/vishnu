"""Isolated HTTPS qualification fixture. Test-only; never deploy with production secrets.

Usage: openssl req -x509 -newkey rsa:2048 -nodes -keyout key.pem -out cert.pem
       -days 1 -subj '/CN=localhost'
       python scripts/capability_live_fixture.py --cert cert.pem --key key.pem

Bind localhost only. Use test credentials and generated data. For production-like
client verification use a controlled DNS name and CA-trusted test certificate.
"""
import argparse
import json
import ssl
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = "qualification-only-token"

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Never log request headers, bodies or credential material.
        pass

    def reply(self, status, data, *, extra=None):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/openapi.json":
            return self.reply(200, {"openapi":"3.1.0","info":{"title":"Isolated qualification API","version":"1"},"servers":[{"url":"https://localhost:9443"}],"paths":{"/forecast":{"get":{"summary":"Read isolated forecast","parameters":[{"name":"city","in":"query","required":True,"schema":{"type":"string","maxLength":80}}]}}}})
        if self.path.startswith("/forecast"):
            if self.headers.get("Authorization") != "Bearer " + TOKEN:
                return self.reply(401, {"error":"unauthorized"})
            return self.reply(200, {"forecast":"sunny","source":"isolated-fixture"})
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "https://example.org/")
            self.end_headers()
            return
        if self.path == "/oversized":
            return self.reply(200, {"payload":"x" * 1100000})
        if self.path == "/timeout":
            time.sleep(10)
            return self.reply(200, {"late":True})
        return self.reply(404, {"error":"not_found"})

    def do_POST(self):
        if self.path != "/mcp":
            return self.reply(404, {"error":"not_found"})
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self.reply(401, {"error":"unauthorized"})
        length = int(self.headers.get("Content-Length", "0"))
        if length > 65536:
            return self.reply(413, {"error":"too_large"})
        try:
            request = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            return self.reply(400, {"error":"invalid_json"})
        if request.get("method") == "notifications/initialized":
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        method = request.get("method")
        if method == "initialize":
            result = {"protocolVersion":"2025-11-25","capabilities":{"tools":{}},"serverInfo":{"name":"isolated-qualification","version":"1"}}
        elif method == "tools/list":
            result = {"tools":[{"name":"read_forecast","description":"Read isolated test data","inputSchema":{"type":"object","properties":{"city":{"type":"string","maxLength":80}},"required":["city"],"additionalProperties":False},"annotations":{"readOnlyHint":True}}]}
        elif method == "tools/call":
            params = request.get("params") or {}
            args = params.get("arguments") or {}
            if params.get("name") != "read_forecast" or not isinstance(args.get("city"),str) or len(args["city"]) > 80 or set(args) != {"city"}:
                return self.reply(200, {"jsonrpc":"2.0","id":request.get("id"),"error":{"code":-32602,"message":"Invalid params"}})
            result = {"content":[{"type":"text","text":json.dumps({"city":args["city"],"forecast":"sunny"})}],"isError":False}
        else:
            return self.reply(200, {"jsonrpc":"2.0","id":request.get("id"),"error":{"code":-32601,"message":"Method not found"}})
        return self.reply(200, {"jsonrpc":"2.0","id":request.get("id"),"result":result})

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--cert", required=True)
    parser.add_argument("--key", required=True)
    parser.add_argument("--port", type=int, default=9443)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(args.cert, args.key)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()
