import asyncio
import struct
import logging
from typing import Optional, Callable, Any

from .razorlink import (
    RazorFrame,
    RazorCrypto,
    RazorLinkSequencer,
    TYPE_RAZOR_COMMAND,
    TYPE_RAZOR_RESPONSE,
    TYPE_HEARTBEAT,
    TYPE_ERROR,
    encode_frame,
    decode_frame,
)

_LOGGER = logging.getLogger("razor-mesh.protocol")


class RazorBluetoothTransport:
    """
    Production-grade async transport for RAZOR-LINK protocol over any
    asyncio.StreamReader / StreamWriter pair (RFCOMM, TCP-over-BLE shim,
    bleak + stream wrapper, raw socket, etc.).

    Features:
    - AES-GCM encryption when crypto is provided
    - 4-byte length prefix for encrypted variable-length frames
    - Automatic sequence number management
    - Heartbeat sending & receiving
    - Request/response pattern with timeouts
    - Graceful shutdown
    """

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        crypto: Optional[RazorCrypto] = None,
        heartbeat_interval: float = 30.0,
    ):
        self._reader = reader
        self._writer = writer
        self._crypto = crypto
        self._heartbeat_interval = heartbeat_interval
        self._running = False
        self._sequencer = RazorLinkSequencer()

        self._heartbeat_task: Optional[asyncio.Task] = None
        self._response_waiters: dict[int, asyncio.Future[RazorFrame]] = {}

        # User-provided callbacks
        self._on_heartbeat: Optional[Callable[[], None]] = None
        self._on_error: Optional[Callable[[RazorFrame], None]] = None
        self._on_command: Optional[Callable[[RazorFrame], Any]] = None

    def start(self) -> None:
        """Start background heartbeat and dispatch loops."""
        if self._running:
            return
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._dispatch_loop())

    def stop(self) -> None:
        """Gracefully stop the transport."""
        self._running = False
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        for fut in self._response_waiters.values():
            if not fut.done():
                fut.set_result(None)  # or set_exception if preferred
        self._writer.close()

    # =======================
    # Callback registration
    # =======================
    def set_heartbeat_handler(self, handler: Callable[[], None]) -> None:
        self._on_heartbeat = handler

    def set_error_handler(self, handler: Callable[[RazorFrame], None]) -> None:
        self._on_error = handler

    def set_command_handler(self, handler: Callable[[RazorFrame], Any]) -> None:
        self._on_command = handler

    # =======================
    # Sending methods
    # =======================
    async def _send_bytes(self, blob: bytes) -> None:
        try:
            self._writer.write(blob)
            await self._writer.drain()
        except Exception as e:
            _LOGGER.error("Write error: %s", e)
            self.stop()

    async def send_command_bytes(self, cmd_bytes: bytes) -> int:
        """Send a RAZOR_COMMAND and return its sequence number."""
        seq = self._sequencer.next()
        frame = RazorFrame(frame_type=TYPE_RAZOR_COMMAND, seq=seq, payload=cmd_bytes)
        blob = self._crypto.encrypt_frame(frame) if self._crypto else encode_frame(frame)

        if self._crypto:
            prefixed = struct.pack(">I", len(blob)) + blob
            await self._send_bytes(prefixed)
        else:
            await self._send_bytes(blob)

        return seq

    async def send_and_await_response(
        self,
        cmd_bytes: bytes,
        timeout: float = 10.0
    ) -> RazorFrame:
        """Send command and wait for matching response by seq."""
        seq = await self.send_command_bytes(cmd_bytes)
        fut: asyncio.Future[RazorFrame] = asyncio.get_running_loop().create_future()
        self._response_waiters[seq] = fut

        try:
            return await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self._response_waiters.pop(seq, None)
            raise
        except asyncio.CancelledError:
            self._response_waiters.pop(seq, None)
            raise

    async def send_response(self, seq: int, payload: bytes) -> None:
        """Send RAZOR_RESPONSE with given seq."""
        frame = RazorFrame(frame_type=TYPE_RAZOR_RESPONSE, seq=seq, payload=payload)
        blob = self._crypto.encrypt_frame(frame) if self._crypto else encode_frame(frame)

        if self._crypto:
            prefixed = struct.pack(">I", len(blob)) + blob
            await self._send_bytes(prefixed)
        else:
            await self._send_bytes(blob)

    async def send_heartbeat(self) -> None:
        """Send TYPE_HEARTBEAT frame."""
        frame = RazorFrame(frame_type=TYPE_HEARTBEAT, seq=self._sequencer.next(), payload=b"")
        blob = self._crypto.encrypt_frame(frame) if self._crypto else encode_frame(frame)

        if self._crypto:
            prefixed = struct.pack(">I", len(blob)) + blob
            await self._send_bytes(prefixed)
        else:
            await self._send_bytes(blob)

    # =======================
    # Receiving frames
    # =======================
    async def _read_frame_bytes(self) -> bytes:
        """Read one complete frame blob from the stream."""
        if self._crypto:
            # Encrypted: 4-byte big-endian length + blob
            length_bytes = await self._reader.readexactly(4)
            length = struct.unpack(">I", length_bytes)[0]
            return await self._reader.readexactly(length)
        else:
            # Plain: fixed header + payload + CRC16
            header = await self._reader.readexactly(8)
            _, _, _, _, length = struct.unpack(">2s B B H H", header)
            rest = await self._reader.readexactly(length + 2)
            return header + rest

    # =======================
    # Background loops
    # =======================
    async def _dispatch_loop(self) -> None:
        """Continuously read and dispatch incoming frames."""
        while self._running:
            try:
                wire_bytes = await self._read_frame_bytes()
            except Exception as e:
                _LOGGER.error("Stream read error: %s", e)
                break

            try:
                frame = self._crypto.decrypt_frame(wire_bytes) if self._crypto else decode_frame(wire_bytes)
            except Exception as e:
                _LOGGER.warning("Frame decode failed: %s", e)
                continue

            # Dispatch by type
            if frame.frame_type == TYPE_RAZOR_RESPONSE:
                fut = self._response_waiters.pop(frame.seq, None)
                if fut and not fut.done():
                    fut.set_result(frame)
                else:
                    _LOGGER.debug("Unsolicited response seq=%d", frame.seq)

            elif frame.frame_type == TYPE_ERROR:
                if self._on_error:
                    self._on_error(frame)

            elif frame.frame_type == TYPE_HEARTBEAT:
                if self._on_heartbeat:
                    self._on_heartbeat()

            else:
                # Commands or other types
                if self._on_command:
                    try:
                        self._on_command(frame)
                    except Exception as e:
                        _LOGGER.error("Command handler failed: %s", e)

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat sender."""
        while self._running:
            await asyncio.sleep(self._heartbeat_interval)
            if not self._running:
                break
            try:
                await self.send_heartbeat()
            except Exception as e:
                _LOGGER.warning("Heartbeat send failed: %s", e)

    async def wait_closed(self) -> None:
        """Wait for the underlying writer to fully close."""
        await self._writer.wait_closed()
