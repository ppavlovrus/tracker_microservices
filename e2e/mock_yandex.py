"""Minimal mock of the Yandex OAuth endpoints for e2e tests.

Stdlib only, no dependencies. Serves:
  POST /token          -> access token for the expected code
  GET  /info?format=…  -> a fixed user profile for the expected token

Run:  python3 e2e/mock_yandex.py [port]
"""

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

EXPECTED_CODE = "e2e-auth-code"
ACCESS_TOKEN = "e2e-access-token"
PROFILE = {
    "id": "987654321",
    "login": "e2e.tester",
    "default_email": "e2e.tester@yandex.ru",
}


class MockYandexHandler(BaseHTTPRequestHandler):
    def _reply(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if urlparse(self.path).path != "/token":
            return self._reply(404, {"error": "not found"})
        length = int(self.headers.get("Content-Length", 0))
        form = parse_qs(self.rfile.read(length).decode())
        if form.get("code") != [EXPECTED_CODE]:
            return self._reply(400, {"error": "bad_verification_code"})
        if not form.get("client_id") or not form.get("client_secret"):
            return self._reply(400, {"error": "invalid_client"})
        self._reply(200, {"access_token": ACCESS_TOKEN, "token_type": "bearer"})

    def do_GET(self):
        if urlparse(self.path).path != "/info":
            return self._reply(404, {"error": "not found"})
        if self.headers.get("Authorization") != f"OAuth {ACCESS_TOKEN}":
            return self._reply(401, {"error": "invalid_token"})
        self._reply(200, PROFILE)

    def log_message(self, fmt, *args):
        print(f"[mock-yandex] {fmt % args}")


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9500
    print(f"[mock-yandex] listening on :{port}")
    HTTPServer(("0.0.0.0", port), MockYandexHandler).serve_forever()
