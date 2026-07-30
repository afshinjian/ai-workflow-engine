"""A minimal, dependency-free ASGI test client.

`starlette.testclient.TestClient` requires an HTTP client package this repository does not pin
(`httpx`/`httpx2`) — DASH-004's Allowed list permits only `fastapi`, `jinja2`, and `uvicorn`
(`ARCHITECTURE.md` §1, §6; OD-D9/DD-09). This drives `SecurityMiddleware`/the API/the web routes
directly over the ASGI protocol instead: no socket, no thread, no new dependency, and it exercises
exactly the callable Uvicorn would invoke in production.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass, field
from http.cookies import SimpleCookie
from typing import Any

from starlette.types import ASGIApp

__all__ = ["AsgiResponse", "AsgiTestClient"]


@dataclass(frozen=True)
class AsgiResponse:
    status: int
    headers: tuple[tuple[str, str], ...]
    body: bytes

    def header(self, name: str) -> str | None:
        lowered = name.lower()
        for key, value in self.headers:
            if key.lower() == lowered:
                return value
        return None

    @property
    def text(self) -> str:
        return self.body.decode("utf-8")

    def json(self) -> Any:
        return json.loads(self.body)


@dataclass
class AsgiTestClient:
    """A tiny stateful client: tracks cookies across requests, like a browser session."""

    app: ASGIApp
    host: str = "127.0.0.1"
    port: int = 8642
    _cookies: dict[str, str] = field(default_factory=dict)

    def get(self, path: str, *, headers: Mapping[str, str] | None = None) -> AsgiResponse:
        return self.request("GET", path, headers=headers)

    def post(
        self,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes = b"",
    ) -> AsgiResponse:
        return self.request("POST", path, headers=headers, body=body)

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes = b"",
    ) -> AsgiResponse:
        return asyncio.run(self._request(method, path, headers=headers, body=body))

    async def _request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None,
        body: bytes,
    ) -> AsgiResponse:
        caller_headers = {key.lower(): value for key, value in (headers or {}).items()}
        host_value = caller_headers.pop("host", f"{self.host}:{self.port}")
        raw_headers: list[tuple[bytes, bytes]] = [(b"host", host_value.encode())]
        if self._cookies:
            cookie_header = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
            raw_headers.append((b"cookie", cookie_header.encode()))
        for key, value in caller_headers.items():
            raw_headers.append((key.encode(), value.encode()))

        query = ""
        if "?" in path:
            path, query = path.split("?", 1)

        scope: dict[str, Any] = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": query.encode(),
            "headers": raw_headers,
            "client": ("127.0.0.1", 51234),
            "server": (self.host, self.port),
            "state": {},
        }

        sent = False

        async def receive() -> dict[str, Any]:
            nonlocal sent
            if sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}

        messages: list[MutableMapping[str, Any]] = []

        async def send(message: MutableMapping[str, Any]) -> None:
            messages.append(message)

        await self.app(scope, receive, send)

        status = 500
        resp_headers: list[tuple[str, str]] = []
        body_parts: list[bytes] = []
        for message in messages:
            if message["type"] == "http.response.start":
                status = message["status"]
                resp_headers = [
                    (k.decode("latin-1"), v.decode("latin-1")) for k, v in message["headers"]
                ]
            elif message["type"] == "http.response.body":
                body_parts.append(message.get("body", b""))

        for key, value in resp_headers:
            if key.lower() == "set-cookie":
                jar: SimpleCookie = SimpleCookie()
                jar.load(value)
                for name, morsel in jar.items():
                    self._cookies[name] = morsel.value

        return AsgiResponse(status=status, headers=tuple(resp_headers), body=b"".join(body_parts))
