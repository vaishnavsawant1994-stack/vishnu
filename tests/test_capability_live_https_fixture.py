"""Exercise the isolated HTTPS fixture over real TLS sockets, not mocked HTTP."""
import json
import shutil
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest


def test_live_fixture_https_openapi_and_mcp(tmp_path):
    if not shutil.which("openssl"):
        pytest.skip("openssl is required for isolated HTTPS fixture")
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(cert), "-days", "1", "-subj", "/CN=localhost"], check=True, capture_output=True, timeout=20)
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    process = subprocess.Popen([sys.executable, "scripts/capability_live_fixture.py", "--cert", str(cert), "--key", str(key), "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    context = ssl.create_default_context(cafile=str(cert))
    base = f"https://localhost:{port}"

    def request(path, *, data=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
        return urllib.request.urlopen(req, context=context, timeout=3)

    try:
        for _ in range(50):
            try:
                with request("/openapi.json") as response:
                    assert json.load(response)["openapi"] == "3.1.0"
                break
            except (OSError, urllib.error.URLError):
                time.sleep(0.1)
        else:
            pytest.fail("HTTPS fixture failed to start")
        with pytest.raises(urllib.error.HTTPError) as error:
            request("/forecast?city=Oslo")
        assert error.value.code == 401
        with request("/forecast?city=Oslo", token="qualification-only-token") as response:
            assert json.load(response)["forecast"] == "sunny"
        with request("/mcp", token="qualification-only-token", data={"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}) as response:
            assert json.load(response)["result"]["protocolVersion"] == "2025-11-25"
        with request("/mcp", token="qualification-only-token", data={"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}) as response:
            assert json.load(response)["result"]["tools"][0]["name"] == "read_forecast"
        with request("/mcp", token="qualification-only-token", data={"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"read_forecast","arguments":{"city":"Oslo"}}}) as response:
            assert json.load(response)["result"]["isError"] is False
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
