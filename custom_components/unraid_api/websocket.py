"""WebSocket client for Unraid GraphQL subscriptions using graphql-transport-ws protocol."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
from typing import TYPE_CHECKING, Any

import aiohttp

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

_LOGGER = logging.getLogger(__name__)

_COMPLETE = object()

# Reconnection settings
_INITIAL_BACKOFF = 1.0
_MAX_BACKOFF = 60.0
_BACKOFF_MULTIPLIER = 2.0


class UnraidWebSocketError(Exception):
    """Raised when a WebSocket operation fails."""


class UnraidWebSocketClient:
    """GraphQL WebSocket client implementing the graphql-transport-ws protocol."""

    def __init__(
        self,
        host: str,
        api_key: str,
        session: aiohttp.ClientSession,
        verify_ssl: bool = True,
    ) -> None:
        self._host = host.rstrip("/")
        self._api_key = api_key
        self._session = session
        self._verify_ssl = verify_ssl
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._subscriptions: dict[str, asyncio.Queue[Any]] = {}
        self._next_id: int = 0
        self._connected = asyncio.Event()
        self._receive_task: asyncio.Task[None] | None = None
        self._shutdown = False

    @property
    def is_connected(self) -> bool:
        """Return whether the WebSocket is connected."""
        return self._connected.is_set()

    def _get_ws_url(self) -> str:
        """Convert HTTP(S) URL to WS(S) URL."""
        url = self._host.replace("https://", "wss://").replace("http://", "ws://")
        return f"{url}/graphql"

    async def connect(self) -> None:
        """Establish WebSocket connection and perform graphql-transport-ws handshake."""
        ws_url = self._get_ws_url()
        ssl_context: ssl.SSLContext | bool | None = None
        if ws_url.startswith("wss://"):
            if self._verify_ssl:
                ssl_context = ssl.create_default_context()
            else:
                ssl_context = False

        _LOGGER.debug("Connecting to WebSocket at %s", ws_url)
        self._ws = await self._session.ws_connect(
            ws_url,
            protocols=["graphql-transport-ws"],
            headers={
                "x-api-key": self._api_key,
                "Origin": self._host,
            },
            ssl=ssl_context,
            heartbeat=30.0,
        )

        # Send connection_init
        await self._send({"type": "connection_init", "payload": {}})

        # Wait for connection_ack
        msg = await self._recv()
        if msg is None or msg.get("type") != "connection_ack":
            raise UnraidWebSocketError(
                f"Expected connection_ack, got {msg.get('type') if msg else 'nothing'}"
            )

        self._connected.set()
        self._receive_task = asyncio.create_task(self._receive_loop())
        _LOGGER.info("WebSocket connected to %s", ws_url)

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        self._shutdown = True
        self._connected.clear()

        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        # Signal all subscription queues to stop
        for queue in self._subscriptions.values():
            await queue.put(_COMPLETE)
        self._subscriptions.clear()

        if self._ws and not self._ws.closed:
            await self._ws.close()
            _LOGGER.debug("WebSocket disconnected")

        self._ws = None

    async def subscribe(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Subscribe to a GraphQL subscription. Yields data payloads."""
        if not self.is_connected:
            raise UnraidWebSocketError("WebSocket is not connected")

        sub_id = str(self._next_id)
        self._next_id += 1
        queue: asyncio.Queue[Any] = asyncio.Queue()
        self._subscriptions[sub_id] = queue

        await self._send({
            "type": "subscribe",
            "id": sub_id,
            "payload": {"query": query, "variables": variables or {}},
        })

        try:
            while True:
                data = await queue.get()
                if data is _COMPLETE:
                    break
                yield data
        finally:
            self._subscriptions.pop(sub_id, None)
            if self._ws and not self._ws.closed:
                try:
                    await self._send({"type": "complete", "id": sub_id})
                except Exception:
                    pass

    async def _send(self, data: dict[str, Any]) -> None:
        """Send a JSON message over the WebSocket."""
        if self._ws is None or self._ws.closed:
            raise UnraidWebSocketError("WebSocket is not connected")
        await self._ws.send_json(data)

    async def _recv(self) -> dict[str, Any] | None:
        """Receive a single JSON message from the WebSocket."""
        if self._ws is None:
            return None
        msg = await self._ws.receive()
        if msg.type == aiohttp.WSMsgType.TEXT:
            return json.loads(msg.data)
        if msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
            return None
        return None

    async def _receive_loop(self) -> None:
        """Process incoming WebSocket messages and dispatch to subscription queues."""
        if self._ws is None:
            return

        try:
            async for msg in self._ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    await self._handle_message(data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    _LOGGER.error("WebSocket error: %s", self._ws.exception())
                    break
                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    break
        except asyncio.CancelledError:
            raise
        except Exception:
            _LOGGER.exception("Unexpected error in WebSocket receive loop")
        finally:
            self._connected.clear()
            # Signal all subscriptions that the connection is lost
            for queue in self._subscriptions.values():
                try:
                    queue.put_nowait(_COMPLETE)
                except asyncio.QueueFull:
                    pass
            if not self._shutdown:
                _LOGGER.debug("WebSocket connection lost")

    async def _handle_message(self, data: dict[str, Any]) -> None:
        """Handle a single protocol message."""
        msg_type = data.get("type")
        sub_id = data.get("id")

        if msg_type == "next" and sub_id in self._subscriptions:
            payload = data.get("payload", {}).get("data")
            if payload is not None:
                await self._subscriptions[sub_id].put(payload)
        elif msg_type == "error" and sub_id in self._subscriptions:
            _LOGGER.error("Subscription %s error: %s", sub_id, data.get("payload"))
            await self._subscriptions[sub_id].put(_COMPLETE)
        elif msg_type == "complete" and sub_id in self._subscriptions:
            await self._subscriptions[sub_id].put(_COMPLETE)
        elif msg_type == "ping":
            await self._send({"type": "pong"})
        elif msg_type == "pong":
            pass  # Expected response to our pings
        elif msg_type == "connection_ack":
            pass  # Already handled during connect
        else:
            _LOGGER.debug("Unhandled WebSocket message type: %s", msg_type)
