"""Utility helpers for Modbus-like framing used by RENAC devices."""

import logging
from dataclasses import dataclass
from typing import Literal

from renac_ble.register import RegisterBlock

logger = logging.getLogger(__name__)

SLAVE_ID = 0x01
READ_REGISTER_CODE = 0x03
WRITE_REGISTER_CODE = 0x06
WRITE_MULTIPLE_REGISTERS_CODE = 0x10


def crc16(data: bytes) -> bytes:
    """Return payload with appended Modbus CRC16 checksum."""

    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            if crc & 0x0001:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return data + crc.to_bytes(2, byteorder="little")


def validate_crc(data: bytes) -> bool:
    """Validate the trailing CRC of ``data``."""

    if len(data) < 3:
        return False
    payload, received_crc = data[:-2], data[-2:]
    expected_crc = crc16(payload)[-2:]
    return received_crc == expected_crc


def build_read_request(address: int, count: int) -> bytes:
    """Construct a Modbus read request for ``count`` registers."""

    return crc16(
        bytes(
            [
                SLAVE_ID,
                READ_REGISTER_CODE,
                (address >> 8) & 0xFF,
                address & 0xFF,
                (count >> 8) & 0xFF,
                count & 0xFF,
            ]
        )
    )


def build_write_request(address: int, value: int) -> bytes:
    """Construct a Modbus write request for a single register."""

    request = bytes(
        [
            SLAVE_ID,
            WRITE_REGISTER_CODE,
            (address >> 8) & 0xFF,
            address & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
        ]
    )
    return crc16(request)


def build_write_multiple_request(address: int, data: bytes) -> bytes:
    """Construct a Modbus write request (FC16) for consecutive registers."""

    if not data or len(data) % 2:
        raise ValueError("data must be a non-empty, even number of bytes")
    count = len(data) // 2
    return crc16(
        bytes(
            [
                SLAVE_ID,
                WRITE_MULTIPLE_REGISTERS_CODE,
                (address >> 8) & 0xFF,
                address & 0xFF,
                (count >> 8) & 0xFF,
                count & 0xFF,
                len(data),
            ]
        )
        + bytes(data)
    )


Fmt =Literal["ascii", "uint16", "int16", "uint32", "int32", "custom"]


def parse_value(
    data: bytes, fmt: Fmt, scale: float = 1.0, *, precision: int | None = None,
) -> str | float | bytes:
    """Parse ``data`` according to ``fmt`` and scaling factor."""

    if fmt == "ascii":
        return data.decode("ascii", errors="ignore").strip("\x00 ")
    elif fmt in ("uint16", "uint32", "int16", "int32"):
        value = int.from_bytes(data, byteorder="big", signed=fmt.startswith("int")) * scale
        if precision is not None and scale % 1:
            return round(value, precision)
        return int(value)
    elif fmt == "custom":
        return data  # leave for manual handling
    else:
        raise ValueError(f"Unsupported format: {fmt}")


def parse_response(data: bytes, fmt: Fmt, count: int, scale: float) -> float:
    """Parse a Modbus response for a single value."""

    expected_len = count * 2
    if len(data) < expected_len:
        raise ValueError("Not enough data in response")
    return parse_value(data[:expected_len], fmt, scale)


def parse_block_response(data: bytes, block: RegisterBlock) -> dict:
    """Parse a block of registers according to ``block`` definition."""

    result = {}
    for field in block["fields"]:
        raw = data[field["offset"] : field["offset"] + field["length"]]
        result[field["name"]] = parse_value(
            raw, field["fmt"], field["scale"], precision=block.get("precision"),
        )
    return result


def validate_write_response(data: bytes, expected_address: int, expected_value: int) -> bool:
    """Validate a Modbus write response against expected values.

    Note: This function is currently unused but kept for potential future use
    if more robust write response validation is needed.
    """

    if len(data) < 6:
        logger.warning("Not enough data to validate write response")
        return False

    function_code = data[1]
    if function_code != 0x06:
        logger.warning("Unexpected function code: %s", function_code)
        return False

    addr = int.from_bytes(data[2:4], "big")
    val = int.from_bytes(data[4:6], "big")

    return addr == expected_address and val == expected_value


INVALID = "invalid"
EXCEPTION_NAMES = {
    1: "ILLEGAL FUNCTION",
    2: "ILLEGAL DATA ADDRESS",
    3: "ILLEGAL DATA VALUE",
    4: "SERVER DEVICE FAILURE",
    5: "ACKNOWLEDGE",
    6: "SERVER DEVICE BUSY",
    8: "MEMORY PARITY ERROR",
    10: "GATEWAY PATH UNAVAILABLE",
    11: "GATEWAY TARGET DEVICE FAILED TO RESPOND",
}


def frame_length(buf: bytes) -> int | None | Literal["invalid"]:
    """Return the expected frame size, or whether its header is incomplete/invalid."""
    if len(buf) < 2:
        return None
    if buf[0] != SLAVE_ID:
        return INVALID
    fc = buf[1]
    if fc & 0x80 and fc & 0x7F in (0x03, 0x06, 0x10):
        return 5
    if fc in (0x06, 0x10):
        return 8
    if fc == 0x03:
        if len(buf) < 3:
            return None
        count = buf[2]
        return 5 + count if count and count <= 250 and not count % 2 else INVALID
    return INVALID


@dataclass(frozen=True)
class Frame:
    data: bytes


@dataclass(frozen=True)
class BadCrc:
    data: bytes


@dataclass(frozen=True)
class Garbage:
    data: bytes


class ModbusFrameBuffer:
    """Extract CRC-validated frames from a stream of notification bytes."""

    def __init__(self) -> None:
        self.pending = b""

    def clear(self) -> None:
        self.pending = b""

    def skip(self, count: int = 1) -> None:
        self.pending = self.pending[count:]

    def feed(self, data: bytes) -> list[Frame | BadCrc | Garbage]:
        self.pending += bytes(data)
        events = []
        garbage = bytearray()
        while self.pending:
            size = frame_length(self.pending)
            if size == INVALID:
                garbage.append(self.pending[0])
                self.skip()
                continue
            if size is None or len(self.pending) < size:
                break
            candidate = self.pending[:size]
            if validate_crc(candidate):
                if garbage:
                    events.append(Garbage(bytes(garbage)))
                    garbage.clear()
                events.append(Frame(candidate))
                self.skip(size)
            else:
                if garbage:
                    events.append(Garbage(bytes(garbage)))
                    garbage.clear()
                events.append(BadCrc(candidate))
                self.skip()
        if garbage:
            events.append(Garbage(bytes(garbage)))
        return events


def response_matches(request: bytes, frame: bytes) -> Literal["ok", "exception"] | None:
    """Match a response header to the request, without requiring a complete frame."""
    if len(frame) < 2 or frame[0] != SLAVE_ID:
        return None
    fc = request[1]
    if frame[1] == fc | 0x80:
        return "exception"
    if frame[1] != fc:
        return None
    if fc == READ_REGISTER_CODE:
        if len(frame) >= 3 and frame[2] == 2 * int.from_bytes(request[4:6], "big"):
            return "ok"
    elif fc in (WRITE_REGISTER_CODE, WRITE_MULTIPLE_REGISTERS_CODE):
        if len(frame) >= 4 and frame[2:4] == request[2:4]:
            return "ok"
    return None
