"""Local-only HTTPS fixture for end-to-end capability bridge qualification."""
import argparse
import json
import ssl
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

TOKEN = "qualification-only-token"


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Deliberately suppress default logs; they must never include credentials.
        pass

    def reply(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if self.path == "/openapi.json":
            api = {
                "openapi": "3.1.0",
                "info": {"title": "Isolated qualification API", "version": "1"},
                "servers": [{"url": f"https://localhost:{self.server.server_port}"}],
                "paths": {
                    "/forecast": {"get": {"summary": "Read isolated forecast", "parameters": [
                        {"name": "city", "in": "query", "required": True,
                         "schema": {"type": "string", "maxLength": 80}},
                    ]}},
                    "/redirect": {"get": {"summary": "Redirect failure scenario"}},
                    "/oversized": {"get": {"summary": "Oversized response scenario"}},
                    "/timeout": {"get": {"summary": "Timeout failure scenario"}},
                },
            }
            return self.reply(200, api)
        if self.path.startswith("/forecast"):
            if self.headers.get("Authorization") != "Bearer " + TOKEN:
                return self.reply(401, {"error": "unauthorized"})
            return self.reply(200, {"forecast": "sunny", "source": "isolated-fixture"})
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "https://example.org/")
            self.end_headers()
            return
        if self.path == "/oversized":
            return self.reply(200, {"payload": "x" * 1_100_000})
        if self.path == "/timeout":
            time.sleep(10)
            return self.reply(200, {"late": True})
        return self.reply(404, {"error": "not_found"})

    def do_POST(self):
        if self.path != "/mcp":
            return self.reply(404, {"error": "not_found"})
        if self.headers.get("Authorization") != "Bearer " + TOKEN:
            return self.reply(401, {"error": "unauthorized"})
        length = int(self.headers.get("Content-Length", "0"))
        if length > 65_536:
            return self.reply(413, {"error": "too_large"})
        try:
            request = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeDecodeError):
            return self.reply(400, {"error": "invalid_json"})
        if request.get("method") == "notifications/initialized":
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        method = request.get("method")
        if method == "initialize":
            result = {"protocolVersion": "2025-11-25", "capabilities": {"tools": {}},
                      "serverInfo": {"name": "isolated-qualification", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": [{
                "name": "read_forecast", "description": "Read isolated test data",
                "inputSchema": {"type": "object", "properties": {"city": {"type": "string", "maxLength": 80}},
                                "required": ["city"], "additionalProperties": False},
                "annotations": {"readOnlyHint": True},
            }]}
        elif method == "tools/call":
            params = request.get("params") or {}
            args = params.get("arguments") or {}
            if (params.get("name") != "read_forecast" or not isinstance(args.get("city"), str)
                    or len(args["city"]) > 80 or set(args) != {"city"}):
                return self.reply(200, {"jsonrpc": "2.0", "id": request.get("id"),
                                        "error": {"code": -32602, "message": "Invalid params"}})
            result = {"content": [{"type": "text", "text": json.dumps({"city": args["city"], "forecast": "sunny"})}],
                      "isError": False}
        else:
            return self.reply(200, {"jsonrpc": "2.0", "id": request.get("id"),
                                    "error": {"code": -32601, "message": "Method not found"}})
        return self.reply(200, {"jsonrpc": "2.0", "id": request.get("id"), "result": result})


def main():
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


if __name__ == "__main__":
    main()
