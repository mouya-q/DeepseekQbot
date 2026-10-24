#!/usr/bin/env python3
"""Minimal RFC 6455 WebSocket client — pure stdlib, no third-party deps.

Built because proot containers block thread creation (uv_thread_create fails),
so npm/pip/websockets cannot be installed. asyncio + raw sockets only.
"""

import asyncio
import base64
import hashlib
import os
import socket
import struct
import sys
from typing import Optional, Tuple


class WebSocketError(Exception):
    pass


class WebSocketClosedError(WebSocketError):
    pass


class WebSocketClient:
    """Minimal async WebSocket client using only Python stdlib."""

    def __init__(
        self,
        url: str,
        on_message: callable,
        on_open: callable = None,
        on_close: callable = None,
        headers: dict = None,
        reconnect_delay: float = 3.0,
        max_reconnect_delay: float = 60.0,
    ):
        self.url = url
        self.on_message = on_message
        self.on_open = on_open
        self.on_close = on_close
        self.headers = headers or {}
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay

        # Parse URL
        if url.startswith("ws://"):
            self.secure = False
            self.host_port = url[5:]
        elif url.startswith("wss://"):
            self.secure = True
            self.host_port = url[6:]
        else:
            raise WebSocketError(f"Unsupported URL scheme: {url}")

        if "/" in self.host_port:
            self.path = "/" + self.host_port.split("/", 1)[1]
            self.host_port = self.host_port.split("/", 1)[0]
        else:
            self.path = "/"

        if ":" in self.host_port:
            self.host, port_str = self.host_port.rsplit(":", 1)
            self.port = int(port_str)
        else:
            self.host = self.host_port
            self.port = 443 if self.secure else 80

        self._reader: asyncio.StreamReader = None
        self._writer: asyncio.StreamWriter = None
        self._running = False
        self._closing = False
        self._frame_buffer = bytearray()
        self._current_task: asyncio.Task = None

    async def connect(self) -> bool:
        """Establish TCP/TLS connection and perform WS handshake."""
        try:
            if self.secure:
                import ssl

                ssl_ctx = ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port, ssl=ssl_ctx),
                    timeout=15.0,
                )
            else:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=15.0
                )

            await self._handshake()
            return True
        except Exception as e:
            print(f"[ws] connect failed: {e}", flush=True)
            await self._cleanup()
            return False

    async def _handshake(self):
        """Perform RFC 6455 handshake."""
        key_bytes = os.urandom(16)
        sec_key = base64.b64encode(key_bytes).decode("ascii")

        req = (
            f"GET {self.path} HTTP/1.1\r\n"
            f"Host: {self.host}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {sec_key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
        )
        for k, v in self.headers.items():
            req += f"{k}: {v}\r\n"
        req += "\r\n"

        self._writer.write(req.encode())
        await self._writer.drain()

        # Read response headers (end with \r\n\r\n)
        response = bytearray()
        while True:
            chunk = await self._reader.read(4096)
            if not chunk:
                raise WebSocketError("Handshake: connection closed")
            response.extend(chunk)
            if b"\r\n\r\n" in response:
                break

        header_text = response.decode("latin-1", errors="replace")
        status_line = header_text.split("\r\n", 1)[0]

        if "101" not in status_line:
            raise WebSocketError(f"Handshake failed: {status_line}")

        if self.on_open:
            await self.on_open()

    async def _recv_frame(self) -> Optional[Tuple[int, bytes]]:
        """Receive one WebSocket frame. Returns (opcode, payload) or None if closed.
        Handles fragmentation: continuation frames are reassembled into the original message."""
        header = await self._reader.readexactly(2)
        fin = (header[0] & 0x80) != 0
        opcode = header[0] & 0x0F
        masked = (header[1] & 0x80) != 0
        payload_len = header[1] & 0x7F

        if payload_len == 126:
            ext = await self._reader.readexactly(2)
            payload_len = struct.unpack("!H", ext)[0]
        elif payload_len == 127:
            ext = await self._reader.readexactly(8)
            payload_len = struct.unpack("!Q", ext)[0]

        if masked:
            mask_key = await self._reader.readexactly(4)
        else:
            mask_key = b"\x00\x00\x00\x00"

        payload = await self._reader.readexactly(payload_len)

        if masked:
            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

        if opcode == 0x8:  # close
            self._closing = True
            return None
        if opcode == 0x9:  # ping
            await self._pong(payload)
            return None
        if opcode == 0xA:  # pong
            return None

        # Handle fragmentation: collect continuation frames (opcode 0x0)
        if opcode == 0x0:
            # Continuation frame — append to buffer
            self._frame_buffer.extend(payload)
            if fin:
                result = bytes(self._frame_buffer)
                self._frame_buffer.clear()
                return 0x1, result  # treat reassembled data as text
            return None  # wait for more continuation frames
        elif not fin and opcode in (0x1, 0x2):
            # Start of a fragmented message
            self._frame_buffer.clear()
            self._frame_buffer.extend(payload)
            return None  # wait for continuation frames
        else:
            return opcode, payload

    async def _pong(self, payload: bytes):
        """Send pong frame."""
        frame = bytearray([0x8A, len(payload)])
        frame += payload
        self._writer.write(bytes(frame))
        try:
            await self._writer.drain()
        except Exception:
            pass

    async def send_text(self, text: str):
        """Send a text frame (auto-fragmented if large). Client frames must be masked per RFC 6455."""
        data = text.encode("utf-8")
        if not self._writer:
            raise WebSocketClosedError("WebSocket not connected")

        max_chunk = 4000
        for i in range(0, len(data), max_chunk):
            chunk = data[i : i + max_chunk]
            first = i == 0
            last = i + max_chunk >= len(data)

            opcode = 0x1 if first else 0x0
            fin_bit = 0x80 if last else 0x0
            length = len(chunk)

            # Client-to-server frames MUST be masked (RFC 6455 §5.3)
            mask_key = os.urandom(4)
            masked_payload = bytes(b ^ mask_key[j % 4] for j, b in enumerate(chunk))

            if length < 126:
                header = bytes([opcode | fin_bit, length | 0x80])
            elif length < 65536:
                header = bytes([opcode | fin_bit, 126 | 0x80]) + struct.pack("!H", length)
            else:
                header = bytes([opcode | fin_bit, 127 | 0x80]) + struct.pack("!Q", length)

            frame = header + mask_key + masked_payload
            self._writer.write(frame)

        await self._writer.drain()

    async def _loop(self):
        """Main receive loop."""
        while self._running and not self._closing:
            try:
                result = await asyncio.wait_for(
                    self._recv_frame(), timeout=30.0
                )
                if result is None:
                    break
                opcode, payload = result
                if opcode == 0x1:  # text
                    try:
                        await self.on_message(payload.decode("utf-8"))
                    except Exception as e:
                        print(f"[ws] on_message error: {e}", flush=True)
            except asyncio.TimeoutError:
                continue
            except asyncio.IncompleteReadError:
                break
            except ConnectionResetError:
                print("[ws] connection reset", flush=True)
                break
            except Exception as e:
                print(f"[ws] recv error: {e}", flush=True)
                break

        self._running = False
        await self._cleanup()
        if self.on_close:
            await self.on_close()

    async def _cleanup(self):
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

    async def run_forever(self):
        """Connect and auto-reconnect."""
        self._running = True
        current_delay = self.reconnect_delay

        while self._running:
            connected = await self.connect()
            if connected:
                current_delay = self.reconnect_delay
                self._current_task = asyncio.create_task(self._loop())
                try:
                    await self._current_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"[ws] loop error: {e}", flush=True)

            if self._running and not self._closing:
                print(f"[ws] reconnecting in {current_delay:.1f}s", flush=True)
                await asyncio.sleep(current_delay)
                current_delay = min(current_delay * 2, self.max_reconnect_delay)

    def stop(self):
        self._running = False
        self._closing = True
        if self._current_task:
            self._current_task.cancel()


# ── simple sync wrapper for health checks ──

def http_get_sync(url: str, timeout: float = 5.0) -> Tuple[int, str]:
    """Synchronous HTTP GET using stdlib only."""
    import urllib.request

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NapCat-Bot/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, str(e)


def http_post_json_sync(url: str, payload: dict, timeout: float = 10.0) -> Tuple[int, str]:
    """Synchronous HTTP POST with JSON body."""
    import urllib.request
    import json

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "NapCat-Bot/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:
        return 0, str(e)