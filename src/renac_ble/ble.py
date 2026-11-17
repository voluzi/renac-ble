"""Core BLE helper used by all RENAC devices."""

import asyncio
import logging
import time
import warnings
from dataclasses import dataclass
from typing import Mapping, Optional, Callable

from bleak import BleakClient
from bleak.exc import BleakError
from bleak.backends.characteristic import BleakGATTCharacteristic

from renac_ble.modbus import (
    EXCEPTION_NAMES,
    SLAVE_ID,
    BadCrc,
    Frame,
    Garbage,
    ModbusFrameBuffer,
    build_read_request,
    parse_response,
    parse_block_response,
    build_write_request,
    frame_length,
    response_matches,
)
from renac_ble.register import Register, RegisterBlock

logger = logging.getLogger(__name__)
frames = logging.getLogger("renac_ble.frames")

NOTIFY_UUID = "0000fec8-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000fed5-0000-1000-8000-00805f9b34fb"


@dataclass
class TransportStats:
    connects: int = 0
    link_losses: int = 0
    requests: int = 0
    retries: int = 0
    timeouts: int = 0
    crc_errors: int = 0
    incomplete: int = 0
    unexpected_frames: int = 0
    exceptions: int = 0


@dataclass
class _Pending:
    request: bytes
    label: str
    future: asyncio.Future
    sent_at: float
    corrupt: bool = False


class _BadResponse(Exception):
    pass


class RenacBLE:
    """Base class providing low level BLE/Modbus communication helpers."""

    request_timeout = 5.0
    read_attempts = 2
    fragment_timeout = 1.0
    settle_delay = 0.5
    _tx_prefix = b""
    _write_response = None
    _reassemble = True
    _unexpected_frame_level = logging.WARNING
    _register_names: Mapping[tuple[int, int], str] = {}

    def __init__(
        self,
        address: str,
        notification_callback: Optional[Callable[[bytes], None]] = None,
        write_uuid: str = WRITE_UUID,
        notify_uuid: str = NOTIFY_UUID,
    ) -> None:
        self.write_uuid = write_uuid
        self.notify_uuid = notify_uuid
        self.address = address
        self.client: Optional[BleakClient] = None
        self._notification_callback = notification_callback
        self._lock = asyncio.Lock()
        self._pending: _Pending | None = None
        self._buffer = ModbusFrameBuffer()
        self._fragment_timer: asyncio.TimerHandle | None = None
        self._needs_settle = False
        self._link_lost = False
        self._disconnect_requested = False
        self._connected_at = None
        self._stats = TransportStats()

    @property
    def stats(self) -> TransportStats:
        return self._stats

    async def connect(self) -> None:
        """Connect to the device and start listening for notifications."""
        started = time.monotonic()
        self._disconnect_requested = False
        self.client = BleakClient(self.address, disconnected_callback=self._on_disconnected)
        await self.client.connect()
        try:
            await self.client.start_notify(self.notify_uuid, self._notify_handler)
        except Exception:
            await self.disconnect()
            raise
        self._link_lost = False
        self._clear_rx()
        self._needs_settle = False
        self._connected_at = time.monotonic()
        self.stats.connects += 1
        mtu = "unknown"
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                mtu = self.client.mtu_size
        except Exception:
            pass
        logger.info("%s: connected in %.1fs (connection #%d, mtu %s)",
                    self.address, time.monotonic() - started, self.stats.connects, mtu)

    def _on_disconnected(self, client: BleakClient) -> None:
        if client is not self.client:
            return
        if not self._disconnect_requested and not self._link_lost:
            self.stats.link_losses += 1
            duration = (f"{time.monotonic() - self._connected_at:.1f}s"
                        if self._connected_at is not None else "unknown duration")
            logger.warning("%s: link lost after %s connected (in flight: %s); reported by BlueZ",
                           self.address, duration, self._pending.label if self._pending else "none")
        self._link_lost = True
        self._fail_pending(ConnectionError(f"{self.address}: link lost"))

    def is_connected(self) -> bool:
        """Return ``True`` if the BLE client is connected."""
        return self.client is not None and not self._link_lost and self.client.is_connected

    async def disconnect(self) -> None:
        """Stop notifications and disconnect, tolerating an already lost link."""
        self._disconnect_requested = True
        self._link_lost = True
        self._fail_pending(ConnectionError(f"{self.address}: disconnected"))
        self._clear_rx()
        if self.client is not None:
            try:
                await self.client.stop_notify(self.notify_uuid)
            except Exception as exc:
                logger.debug("%s: stop_notify failed: %s", self.address, exc)
            try:
                await self.client.disconnect()
            except Exception as exc:
                logger.debug("%s: disconnect failed: %s", self.address, exc)
        logger.info("%s: disconnected; stats: %s", self.address, self.stats)

    def _fail_pending(self, error: Exception) -> None:
        if self._pending is not None and not self._pending.future.done():
            self._pending.future.set_exception(error)

    def _clear_rx(self) -> None:
        if self._fragment_timer is not None:
            self._fragment_timer.cancel()
            self._fragment_timer = None
        self._buffer.clear()

    def describe(self, request: bytes) -> str:
        address = int.from_bytes(request[2:4], "big")
        count = int.from_bytes(request[4:6], "big") if request[1] != 6 else 1
        name = self._register_names.get((address, count))
        label = f"{name}@{address}" if name else str(address)
        if request[1] == 3:
            return f"read {label}x{count}"
        if request[1] == 6:
            return f"write {label}={int.from_bytes(request[4:6], 'big')}"
        return f"write {label}x{count}"

    async def _notify_handler(
        self, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Route notifications through framing and request matching."""
        data = bytes(data)
        frames.debug("%s RX %s", self.address, data.hex(" "))
        if self._pending is None or self._pending.future.done():
            if self._notification_callback:
                self._notification_callback(data)
            else:
                logger.log(self._unexpected_frame_level,
                           "%s: unsolicited frame (no request pending): %s",
                           self.address, data.hex(" "))
            return
        if not self._reassemble:
            self._clear_rx()
        self._route_events(self._buffer.feed(data))
        if not self._reassemble:
            self._clear_rx()

    def _matches(self, request: bytes, frame: bytes) -> str | None:
        return response_matches(request, frame)

    def _route_events(self, events: list[Frame | BadCrc | Garbage]) -> None:
        pending = self._pending
        if pending is None or pending.future.done():
            return
        for event in events:
            data = event.data
            if isinstance(event, Frame):
                if self._matches(pending.request, data):
                    pending.future.set_result(data)
                    self._clear_rx()
                    return
                self.stats.unexpected_frames += 1
                logger.log(self._unexpected_frame_level,
                           "%s: discarding unexpected frame while waiting for %s: %s",
                           self.address, pending.label, data.hex(" "))
            elif isinstance(event, BadCrc):
                self.stats.crc_errors += 1
                if self._matches(pending.request, data):
                    pending.corrupt = True
                    logger.warning("%s %s: corrupt response (CRC mismatch, %d bytes): %s",
                                   self.address, pending.label, len(data), data.hex(" "))
                    self._fail_pending(_BadResponse("crc"))
                    self._clear_rx()
                    return
                logger.debug("%s: CRC mismatch on non-matching candidate: %s",
                             self.address, data.hex(" "))
            else:
                logger.warning("%s: discarding %d bytes of garbage while waiting for %s: %s",
                               self.address, len(data), pending.label, data.hex(" "))
        if self._buffer.pending and self._reassemble:
            if self._fragment_timer is not None:
                self._fragment_timer.cancel()
            self._fragment_timer = asyncio.get_running_loop().call_later(
                self.fragment_timeout, self._on_fragment_timeout,
            )

    def _on_fragment_timeout(self) -> None:
        self._fragment_timer = None
        pending = self._pending
        data = self._buffer.pending
        if pending is None or pending.future.done() or not data:
            return
        self.stats.incomplete += 1
        logger.warning("%s %s: incomplete response after %.1fs: got %d of %s bytes: %s",
                       self.address, pending.label, self.fragment_timeout,
                       len(data), frame_length(data), data.hex(" "))
        if self._matches(pending.request, data) or (
            len(data) < 4 and data[:2] == bytes([SLAVE_ID, pending.request[1]])
        ):
            self._fail_pending(_BadResponse("incomplete"))
            self._clear_rx()
        else:
            self._buffer.skip()
            self._route_events(self._buffer.feed(b""))

    async def _transact(
        self, request: bytes, timeout: float | None = None, *, attempt: int = 1, attempts: int = 1
    ) -> bytes | None:
        if not self.is_connected():
            raise ConnectionError(f"{self.address} is not connected")
        async with self._lock:
            if self._needs_settle:
                # FC03 has no address/transaction ID: same-size replies beyond this window remain ambiguous.
                await asyncio.sleep(self.settle_delay)
                if self._buffer.pending:
                    logger.warning("%s: discarding settled bytes: %s",
                                   self.address, self._buffer.pending.hex(" "))
                self._clear_rx()
                self._needs_settle = False
            if not self.is_connected():
                raise ConnectionError(f"{self.address} is not connected")
            self._clear_rx()
            pending = _Pending(request, self.describe(request),
                               asyncio.get_running_loop().create_future(), time.monotonic())
            self._pending = pending
            self.stats.requests += 1
            payload = self._tx_prefix + request
            frames.debug("%s TX %s: %s", self.address, pending.label, payload.hex(" "))
            timeout = self.request_timeout if timeout is None else timeout
            try:
                try:
                    await self.client.write_gatt_char(self.write_uuid, payload, response=self._write_response)
                except BleakError as exc:
                    raise ConnectionError(f"{self.address}: write failed: {exc}") from exc
                frame = await asyncio.wait_for(pending.future, timeout)
            except asyncio.TimeoutError:
                self.stats.timeouts += 1
                self._needs_settle = True
                logger.warning("%s %s: no response after %.1fs (attempt %d/%d, partial rx: %s)",
                               self.address, pending.label, timeout, attempt, attempts,
                               self._buffer.pending.hex(" "))
                return None
            except _BadResponse:
                self._needs_settle = True
                return None
            except asyncio.CancelledError:
                self._needs_settle = True
                raise
            finally:
                self._pending = None
                self._clear_rx()
                if not pending.future.done():
                    pending.future.cancel()
                elif not pending.future.cancelled():
                    pending.future.exception()
            logger.debug("%s %s: ok in %.0f ms", self.address, pending.label,
                         (time.monotonic() - pending.sent_at) * 1000)
            if frame[1] & 0x80:
                self.stats.exceptions += 1
                logger.warning("%s %s: Modbus exception 0x%02x (%s)", self.address,
                               pending.label, frame[2], EXCEPTION_NAMES.get(frame[2], "unknown"))
            return frame

    async def _write_and_get_response(
        self, payload: bytes, timeout: float = 10.0
    ) -> Optional[bytes]:
        return await self._transact(payload, timeout)

    async def _read_raw(self, address: int, count: int) -> bytes | None:
        request = build_read_request(address, count)
        for attempt in range(1, self.read_attempts + 1):
            if attempt > 1:
                self.stats.retries += 1
            frame = await self._transact(request, attempt=attempt, attempts=self.read_attempts)
            if frame is not None:
                return None if frame[1] & 0x80 else frame[3:-2]
        return None

    async def read_named_register(self, register: Register) -> float | None:
        """Read and parse a single register defined by :class:`Register`."""
        raw = await self._read_raw(register["address"], register["count"])
        if raw is None:
            return None
        try:
            return parse_response(raw, register["fmt"], register["count"], register["scale"])
        except ValueError as exc:
            logger.warning("%s %s: failed to parse response: %s (%s)", self.address,
                           self.describe(build_read_request(register["address"], register["count"])),
                           exc, raw.hex(" "))
            return None

    async def write_named_register(self, register: Register, value: int) -> bool | None:
        """Write once and confirm the echo or a fresh readback."""
        raw = round(value / register["scale"])
        request = build_write_request(register["address"], raw)
        frame = await self._transact(request)
        if frame is not None:
            if frame[1] & 0x80:
                return False
            if frame[4:6] == request[4:6]:
                return True
        readback = await self._read_raw(register["address"], 1)
        actual = (int.from_bytes(readback, "big", signed=register["fmt"] == "int16")
                  if readback is not None else None)
        logger.warning("%s %s: echo %s, readback %s (expected %s)",
                       self.address, self.describe(request),
                       "lost" if frame is None else "differs", actual, raw)
        return actual == raw if actual is not None else None

    async def read_named_register_block(self, block: RegisterBlock) -> dict | None:
        """Read and parse a :class:`RegisterBlock` from the device."""
        raw = await self._read_raw(block["address"], block["count"])
        if raw is None:
            return None
        try:
            return parse_block_response(raw, block)
        except ValueError as exc:
            logger.warning("%s %s: failed to parse block: %s (%s)", self.address,
                           self.describe(build_read_request(block["address"], block["count"])),
                           exc, raw.hex(" "))
            return None
