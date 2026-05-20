"""Reverse proxy to nanobot gateway — makes CoLearn the single entry point.

Proxies /webui/*, /auth/*, and WebSocket upgrades on / to the nanobot
gateway (default http://127.0.0.1:8765). CoLearn's own /api/* routes
are served directly by FastAPI.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

NANOBOT_GATEWAY = os.getenv("COLEARN_NANOBOT_GATEWAY", "http://127.0.0.1:8765")

router = APIRouter()

_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(base_url=NANOBOT_GATEWAY, timeout=30.0)
    return _http_client


@router.api_route("/webui/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
@router.api_route("/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_http(request: Request, path: str) -> StreamingResponse:
    client = _get_http_client()
    url = str(request.url).split(str(request.base_url), 1)[-1]
    headers = dict(request.headers)
    headers.pop("host", None)
    body = await request.body()
    resp = await client.request(
        method=request.method,
        url=f"/{url}",
        headers=headers,
        content=body,
    )
    return StreamingResponse(
        content=iter([resp.content]),
        status_code=resp.status_code,
        headers=dict(resp.headers),
    )


@router.websocket("/")
async def proxy_ws(websocket: WebSocket) -> None:
    """Proxy WebSocket connections to nanobot gateway."""
    await websocket.accept()
    ws_url = NANOBOT_GATEWAY.replace("http://", "ws://").replace("https://", "wss://")
    query = str(websocket.scope.get("query_string", b""), "utf-8")
    target = f"{ws_url}/?{query}" if query else f"{ws_url}/"

    import websockets

    try:
        async with websockets.connect(target) as upstream:
            import anyio

            async def client_to_upstream():
                try:
                    while True:
                        data = await websocket.receive_text()
                        await upstream.send(data)
                except WebSocketDisconnect:
                    await upstream.close()

            async def upstream_to_client():
                try:
                    async for message in upstream:
                        if isinstance(message, str):
                            await websocket.send_text(message)
                        else:
                            await websocket.send_bytes(message)
                except Exception:
                    pass

            async with anyio.create_task_group() as tg:
                tg.start_soon(client_to_upstream)
                tg.start_soon(upstream_to_client)
    except Exception:
        try:
            await websocket.close(code=1011)
        except Exception:
            pass
