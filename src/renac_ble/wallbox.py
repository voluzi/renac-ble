"""Helpers for interacting with RENAC wallbox chargers."""

import asyncio
import logging
import struct
from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Callable, Optional

from bleak.backends.characteristic import BleakGATTCharacteristic

from renac_ble.ble import RenacBLE
from renac_ble.modbus import (
    READ_REGISTER_CODE,
    SLAVE_ID,
    WRITE_MULTIPLE_REGISTERS_CODE,
    build_read_request,
    build_write_multiple_request,
    validate_crc,
)

logger = logging.getLogger(__name__)

# Every frame to and from the wallbox is Modbus RTU wrapped in this prefix.
WALLBOX_PREFIX = b"#SOCKA#"

# Basic settings block, read and written as a whole like the RENAC SEC app does.
BASIC_SETTINGS_ADDRESS = 10200
BASIC_SETTINGS_COUNT = 21
MAX_OUTPUT_CURRENT_OFFSET = 2  # byte offset of the u16, in 0.1 A

MIN_OUTPUT_CURRENT = 6.0  # IEC 61851 lower bound for AC charging
MAX_OUTPUT_CURRENT = 32.0

READ_ATTEMPTS = 2


class ChargingMode(IntEnum):
    """How the wallbox authorises a charging session."""

    APP = 0
    RFID = 1
    PLUG_AND_PLAY = 2


@dataclass
class ChargingWindow:
    """Daily time window in which charging is allowed."""

    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int


class RenacWallboxBLE(RenacBLE):
    """BLE client for RENAC wallbox chargers."""

    def __init__(
        self, address: str, on_notification: Optional[Callable[[dict], None]] = None
    ) -> None:
        self._parsed_callback = on_notification
        self._expect: Optional[Callable[[bytes], bool]] = None
        self._settings_lock = asyncio.Lock()
        self.request_timeout = 10.0
        super().__init__(address)

    async def _notify_handler(
        self, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Route status pushes to the callback and replies to the pending request."""

        data = bytes(data)
        if is_wallbox_notification(data):
            if self._parsed_callback:
                self._parsed_callback(parse_wallbox_notification(data))
        if not data.startswith(WALLBOX_PREFIX):
            return
        frame = data[len(WALLBOX_PREFIX):]
        # The wallbox also pushes unrelated frames (e.g. its clock) right after
        # connecting, so only a frame matching the pending request answers it.
        if self._expect is not None and validate_crc(frame) and self._expect(frame):
            self._last_data = frame
            self._response_event.set()

    async def _request(
        self, frame: bytes, expect: Callable[[bytes], bool]
    ) -> Optional[bytes]:
        """Send a Modbus frame and wait for the reply accepted by ``expect``."""

        if not self.is_connected():
            raise ConnectionError(f"Wallbox {self.address} is not connected")
        async with self._lock:
            self._last_data = None
            self._response_event.clear()
            self._expect = expect
            try:
                await self.client.write_gatt_char(
                    self.write_uuid, WALLBOX_PREFIX + frame, response=False
                )
                await asyncio.wait_for(self._response_event.wait(), timeout=self.request_timeout)
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting for wallbox response")
                return None
            finally:
                self._expect = None
            return self._last_data

    async def _read_registers(self, address: int, count: int) -> Optional[bytes]:
        """Read ``count`` holding registers and return their raw bytes."""

        size = count * 2

        def expect(frame: bytes) -> bool:
            return (
                len(frame) == size + 5
                and frame[0] == SLAVE_ID
                and frame[1] == READ_REGISTER_CODE
                and frame[2] == size
            )

        # Replies are occasionally lost over BLE; a read is safe to repeat.
        for _ in range(READ_ATTEMPTS):
            resp = await self._request(build_read_request(address, count), expect)
            if resp:
                return resp[3:3 + size]
        return None

    async def _write_registers(self, address: int, data: bytes) -> Optional[bool]:
        """Write consecutive registers with FC16 and confirm the echo.

        Returns ``None`` when no reply arrived: the write may still have landed.
        """

        echo = bytes(
            [
                SLAVE_ID,
                WRITE_MULTIPLE_REGISTERS_CODE,
                (address >> 8) & 0xFF,
                address & 0xFF,
                0,
                len(data) // 2,
            ]
        )

        def expect(frame: bytes) -> bool:
            return frame[1] == WRITE_MULTIPLE_REGISTERS_CODE or frame[1] == (
                WRITE_MULTIPLE_REGISTERS_CODE | 0x80
            )

        resp = await self._request(build_write_multiple_request(address, data), expect)
        if resp is None:
            return None
        return resp[:6] == echo

    async def get_basic_settings(self) -> Optional[dict]:
        """Return the parsed basic settings block."""

        raw = await self._read_registers(BASIC_SETTINGS_ADDRESS, BASIC_SETTINGS_COUNT)
        return parse_basic_settings(raw) if raw else None

    async def get_max_output_current(self) -> Optional[float]:
        """Return the configured maximum output current in amperes."""

        settings = await self.get_basic_settings()
        return settings["max_output_current"] if settings else None

    async def set_max_output_current(self, amps: float) -> bool:
        """Set the maximum output current in amperes, keeping other settings."""

        tenths = int(round(float(amps) * 10))
        if not MIN_OUTPUT_CURRENT * 10 <= tenths <= MAX_OUTPUT_CURRENT * 10:
            raise ValueError(
                f"max output current must be between {MIN_OUTPUT_CURRENT} and "
                f"{MAX_OUTPUT_CURRENT} A, got {amps}"
            )
        return await self._update_basic_settings(
            lambda raw: with_max_output_current(raw, tenths / 10)
        )

    async def get_charging_mode(self) -> Optional[ChargingMode]:
        """Return how charging sessions are authorised."""

        settings = await self.get_basic_settings()
        return ChargingMode(settings["charging_mode"]) if settings else None

    async def set_charging_mode(self, mode: ChargingMode) -> bool:
        """Set how charging sessions are authorised (app, RFID or plug and play)."""

        mode = ChargingMode(mode)
        return await self._update_basic_settings(
            lambda raw: struct.pack(">H", mode) + raw[2:]
        )

    async def get_allowed_charging_time(self) -> Optional[ChargingWindow]:
        """Return the daily window in which charging is allowed."""

        raw = await self._read_registers(BASIC_SETTINGS_ADDRESS, BASIC_SETTINGS_COUNT)
        return ChargingWindow(*raw[8:12]) if raw else None

    async def set_allowed_charging_time(self, window: ChargingWindow) -> bool:
        """Set the daily window in which charging is allowed."""

        if not (0 <= window.start_hour <= 23 and 0 <= window.end_hour <= 23
                and 0 <= window.start_minute <= 59 and 0 <= window.end_minute <= 59):
            raise ValueError(f"invalid charging window {window}")
        data = bytes([window.start_hour, window.start_minute, window.end_hour, window.end_minute])
        return await self._update_basic_settings(lambda raw: raw[:8] + data + raw[12:])

    async def _update_basic_settings(self, patch: Callable[[bytes], bytes]) -> bool:
        """Read, patch and write back the basic settings block, then verify it."""

        # The block is written whole, so a concurrent settings write between
        # our read and write would be silently reverted.
        async with self._settings_lock:
            raw = await self._read_registers(BASIC_SETTINGS_ADDRESS, BASIC_SETTINGS_COUNT)
            if raw is None:
                return False
            block = patch(raw)
            if block == raw:
                return True
            # A lost echo is settled by the readback rather than a blind rewrite.
            if await self._write_registers(BASIC_SETTINGS_ADDRESS, block) is False:
                return False
            return await self._read_registers(BASIC_SETTINGS_ADDRESS, BASIC_SETTINGS_COUNT) == block


def with_max_output_current(block: bytes, amps: float) -> bytes:
    """Return a copy of the basic settings ``block`` with a new max current."""

    patched = bytearray(block)
    o = MAX_OUTPUT_CURRENT_OFFSET
    patched[o:o + 2] = struct.pack(">H", int(round(amps * 10)))
    return bytes(patched)


def parse_basic_settings(block: bytes) -> dict:
    """Parse the 10200 basic settings block (register data only)."""

    if len(block) != BASIC_SETTINGS_COUNT * 2:
        raise ValueError(f"expected {BASIC_SETTINGS_COUNT * 2} bytes, got {len(block)}")
    mode, cur, temp, power = struct.unpack(">HHhH", block[0:8])
    begin_h, begin_m, end_h, end_m = block[8:12]
    sampling, meter_address, rate_number = struct.unpack(">HHH", block[12:18])
    rates = []
    for i in range(min(rate_number, 4)):
        o = 18 + i * 6
        b_h, b_m, e_h, e_m = block[o:o + 4]
        (price,) = struct.unpack(">H", block[o + 4:o + 6])
        rates.append(
            {"begin": f"{b_h:02d}:{b_m:02d}", "end": f"{e_h:02d}:{e_m:02d}", "rate": price / 100}
        )
    return {
        "charging_mode": mode,
        "max_output_current": cur / 10,
        "protect_temperature": temp / 10,
        "max_input_power": power,
        "allow_charging_begin": f"{begin_h:02d}:{begin_m:02d}",
        "allow_charging_end": f"{end_h:02d}:{end_m:02d}",
        "external_current_sampling": sampling,
        "meter_address": meter_address,
        "rates": rates,
    }


def is_wallbox_notification(data: bytes) -> bool:
    """Return ``True`` if ``data`` looks like a wallbox notification."""

    if data is None or not data.startswith(b"#SOCKA#") or len(data) < 10:
        return False
    payload = data[7:]
    if len(payload) < 3:
        return False
    return payload[1] == 0x03 and payload[2] == 0x8E


def get_renac_charger_state(code: int) -> str:
    """Map integer status codes to human readable strings."""

    return {
        0: "idle",
        1: "scheduled",
        2: "paused",
        3: "charging",
        4: "completed",
        5: "error"
    }.get(code, "")


def parse_wallbox_notification(data: bytes) -> Optional[dict]:
    """Parse a wallbox notification payload into a dictionary."""

    if not data.startswith(b"#SOCKA#"):
        raise ValueError("Invalid message: missing #SOCKA# header")
    payload = data[7:]  # remove '#SOCKA#'
    result: dict[str, object] = {}
    try:
        result["model"] = payload[3:35].decode("ascii", errors="ignore").strip("\x00").strip()
        result["sn"] = payload[35:67].decode("ascii", errors="ignore").strip("\x00").strip()
        result["manufacturer"] = payload[67:99].decode("ascii", errors="ignore").strip("\x00").strip()

        result["version"] = f'V{struct.unpack(">H", payload[99:101])[0] / 100:.2f}'
        result["state"] = get_renac_charger_state(struct.unpack(">H", payload[101:103])[0])
        result["phase_a_voltage"] = struct.unpack(">H", payload[103:105])[0] / 10
        result["phase_a_current"] = struct.unpack(">H", payload[105:107])[0] / 10
        result["phase_b_voltage"] = struct.unpack(">H", payload[107:109])[0] / 10
        result["phase_b_current"] = struct.unpack(">H", payload[109:111])[0] / 10
        result["phase_c_voltage"] = struct.unpack(">H", payload[111:113])[0] / 10
        result["phase_c_current"] = struct.unpack(">H", payload[113:115])[0] / 10
        result["power"] = struct.unpack(">H", payload[115:117])[0]
        result["temperature"] = struct.unpack(">H", payload[117:119])[0] / 10
        result["current_charging_amount"] = struct.unpack(">H", payload[119:121])[0] / 10
        result["current_charging_time"] = struct.unpack(">H", payload[121:123])[0] / 10
        result["total_charge"] = struct.unpack(">I", payload[127:131])[0] / 10
        result["update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    except Exception as e:  # pragma: no cover - best effort parsing
        logger.exception("Error parsing wallbox notification")
        result["error"] = f"Error parsing: {e}"

    return result
