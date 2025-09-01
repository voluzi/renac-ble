from typing import Literal, Union
from renac_ble.register import RegisterBlock

SLAVE_ID = 0x01
READ_REGISTER_CODE = 0x03
WRITE_REGISTER_CODE = 0x06


def crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for pos in data:
        crc ^= pos
        for _ in range(8):
            if crc & 0x0001:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return data + crc.to_bytes(2, byteorder='little')


def validate_crc(data: bytes) -> bool:
    if len(data) < 3:
        return False
    payload, received_crc = data[:-2], data[-2:]
    expected_crc = crc16(payload)[-2:]
    return received_crc == expected_crc


def build_read_request(address: int, count: int) -> bytes:
    return crc16(bytes([
        SLAVE_ID,
        READ_REGISTER_CODE,
        (address >> 8) & 0xFF,
        address & 0xFF,
        (count >> 8) & 0xFF,
        count & 0xFF,
    ]))


def build_write_request(address: int, value: int) -> bytes:
    request = bytes([
        SLAVE_ID,
        WRITE_REGISTER_CODE,
        (address >> 8) & 0xFF,
        address & 0xFF,
        (value >> 8) & 0xFF,
        value & 0xFF,
    ])
    return crc16(request)


Fmt = Literal["ascii", "uint16", "int16", "uint32", "int32", "custom"]


def parse_value(data: bytes, fmt: Fmt, scale: float = 1.0) -> Union[str, float, bytes]:
    if fmt == "ascii":
        return data.decode("ascii", errors="ignore").strip("\x00 ")
    elif fmt in ("uint16", "uint32"):
        return int(int.from_bytes(data, byteorder="big", signed=False) * scale)
    elif fmt in ("int16", "int32"):
        return int(int.from_bytes(data, byteorder="big", signed=True) * scale)
    elif fmt == "custom":
        return data  # leave for manual handling
    else:
        raise ValueError(f"Unsupported format: {fmt}")


def parse_response(data: bytes, fmt: Fmt, count: int, scale: float) -> float:
    expected_len = count * 2
    if len(data) < expected_len:
        raise ValueError("Not enough data in response")
    return parse_value(data[:expected_len], fmt, scale)


def parse_block_response(data: bytes, block: RegisterBlock) -> dict:
    result = {}
    for field in block["fields"]:
        raw = data[field["offset"]:field["offset"] + field["length"]]
        result[field["name"]] = parse_value(raw, field["fmt"], field["scale"])
    return result


def validate_write_response(data: bytes, expected_address: int, expected_value: int) -> bool:
    if len(data) < 6:
        print("⚠️ Not enough data to validate write response")
        return False

    function_code = data[1]
    if function_code != 0x06:
        print(f"⚠️ Unexpected function code: {function_code}")
        return False

    addr = int.from_bytes(data[2:4], "big")
    val = int.from_bytes(data[4:6], "big")

    return addr == expected_address and val == expected_value
