import asyncio

import pytest

from renac_ble.modbus import build_write_multiple_request, crc16
from renac_ble.wallbox import (
    WALLBOX_PREFIX,
    ChargingMode,
    ChargingWindow,
    RenacWallboxBLE,
    parse_basic_settings,
    with_max_output_current,
)

# Captured from a RENAC EV-AC3P-22K on 2026-09-25.
BASIC_BLOCK = bytes.fromhex(
    "0002014002ee55f00000173b00040001000216000800000f0801153b0017000000000000000000000000"
)
READ_REPLY = bytes.fromhex("01032a") + BASIC_BLOCK + bytes.fromhex("dd1e")
WRITE_ECHO = bytes.fromhex("011027d800158b49")
STATUS_PUSH = bytes.fromhex(
    "23534f434b412301038e52454e41435f5448414953454e30303200000000000000000000000000000000"
    "384450323233313233303931383037310d00000000000000000000000000000052656e61630000000000"
    "000000000000000000000000000000000000000000000068000009ec000009c9000009da00000000014a"
    "00c30000000000000001f55c00000000000000000000000000004d2f"
)
CLOCK_PUSH = bytes.fromhex("23534f434b41230103061a09190c1d2ab09e")


def test_parse_basic_settings():
    s = parse_basic_settings(BASIC_BLOCK)
    assert s["charging_mode"] == 2
    assert s["max_output_current"] == 32.0
    assert s["protect_temperature"] == 75.0
    assert s["max_input_power"] == 22000
    assert (s["allow_charging_begin"], s["allow_charging_end"]) == ("00:00", "23:59")
    assert s["rates"] == [
        {"begin": "22:00", "end": "08:00", "rate": 0.15},
        {"begin": "08:01", "end": "21:59", "rate": 0.23},
    ]


def test_write_frame_matches_device_accepted_bytes():
    block = with_max_output_current(BASIC_BLOCK, 16)
    assert block[2:4] == bytes.fromhex("00a0")
    assert block[:2] == BASIC_BLOCK[:2] and block[4:] == BASIC_BLOCK[4:]
    frame = build_write_multiple_request(10200, block)
    assert frame[:7] == bytes.fromhex("011027d800152a")


class FakeClient:
    """Answers wallbox requests the way the device does, after unrelated pushes."""

    def __init__(self, wallbox, replies):
        self.wallbox = wallbox
        self.replies = replies
        self.writes = []
        self.is_connected = True

    async def write_gatt_char(self, uuid, data, response=None):
        self.writes.append(bytes(data))
        reply = self.replies.pop(0)
        pushes = [STATUS_PUSH, CLOCK_PUSH] + ([WALLBOX_PREFIX + reply] if reply else [])
        for push in pushes:
            asyncio.get_running_loop().call_soon(
                lambda d=push: asyncio.ensure_future(self.wallbox._notify_handler(None, bytearray(d)))
            )


def make_wallbox(replies):
    pushed = []
    wb = RenacWallboxBLE("00:00:00:00:00:00", on_notification=pushed.append)
    wb.client = FakeClient(wb, replies)
    wb.request_timeout = 0.2
    return wb, pushed


def test_read_ignores_unsolicited_frames():
    wb, pushed = make_wallbox([READ_REPLY])
    assert asyncio.run(wb.get_max_output_current()) == 32.0
    assert wb.client.writes[0].startswith(WALLBOX_PREFIX)
    assert pushed and pushed[0]["model"] == "RENAC_THAISEN002"


def test_set_max_output_current_writes_and_verifies():
    # 16.15 A quantizes to 16.2 A on the wire; verification must agree.
    patched = with_max_output_current(BASIC_BLOCK, 16.2)
    reread = crc16(bytes.fromhex("01032a") + patched)

    wb, _ = make_wallbox([READ_REPLY, WRITE_ECHO, reread])
    assert asyncio.run(wb.set_max_output_current(16.15)) is True
    assert wb.client.writes[1] == WALLBOX_PREFIX + build_write_multiple_request(10200, patched)


def test_lost_replies_are_settled_by_readback():
    patched = with_max_output_current(BASIC_BLOCK, 16)
    reread = crc16(bytes.fromhex("01032a") + patched)

    # read lost then retried, write echo lost, readback shows the new value
    wb, _ = make_wallbox([None, READ_REPLY, None, reread])
    assert asyncio.run(wb.set_max_output_current(16)) is True
    assert len(wb.client.writes) == 4  # the write was sent exactly once


def test_set_max_output_current_rejects_out_of_range():
    wb, _ = make_wallbox([])
    with pytest.raises(ValueError):
        asyncio.run(wb.set_max_output_current(40))
    assert wb.client.writes == []


def test_charging_mode_and_window_only_touch_their_fields():
    rfid = bytes.fromhex("0001") + BASIC_BLOCK[2:]
    window = BASIC_BLOCK[:8] + bytes([22, 0, 7, 30]) + BASIC_BLOCK[12:]

    wb, _ = make_wallbox([READ_REPLY, WRITE_ECHO, crc16(bytes.fromhex("01032a") + rfid)])
    assert asyncio.run(wb.set_charging_mode(ChargingMode.RFID)) is True
    assert wb.client.writes[1] == WALLBOX_PREFIX + build_write_multiple_request(10200, rfid)

    wb, _ = make_wallbox([READ_REPLY, WRITE_ECHO, crc16(bytes.fromhex("01032a") + window)])
    assert asyncio.run(wb.set_allowed_charging_time(ChargingWindow(22, 0, 7, 30))) is True
    assert wb.client.writes[1] == WALLBOX_PREFIX + build_write_multiple_request(10200, window)


def test_stop_and_start_send_the_captured_command_frames():
    stop, start = bytes.fromhex("0106283c0002c1a7"), bytes.fromhex("0106283c000181a6")

    async def stop_then_start(wb):
        return await wb.stop_charging(), await wb.start_charging()

    wb, _ = make_wallbox([stop, start])
    assert asyncio.run(stop_then_start(wb)) == (True, True)
    assert wb.client.writes == [WALLBOX_PREFIX + stop, WALLBOX_PREFIX + start]


def test_get_status_parses_like_a_push():
    # The status read returns the pushed block minus its trailing registers.
    data = STATUS_PUSH[10:10 + 138]
    wb, _ = make_wallbox([crc16(bytes([1, 3, 138]) + data)])
    status = asyncio.run(wb.get_status())
    assert status["sn"] == "8DP2231230918071"
    assert status["state"] == "idle"
    assert status["phase_a_voltage"] == 254.0
