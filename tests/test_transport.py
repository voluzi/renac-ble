import asyncio
import time

import pytest
from bleak.exc import BleakError

from renac_ble import ble
from renac_ble.inverter import RenacInverterBLE
from renac_ble.inverter_registers import MIN_SOC, TOTAL_ENERGY_BLOCK, EPS_POWER_BLOCK
from renac_ble.modbus import build_write_request, crc16


def reply(value=20, count=1):
    return crc16(bytes([1, 3, count * 2]) + value.to_bytes(count * 2, 'big'))


class FakeBleakClient:
    def __init__(self, address, disconnected_callback, scripts):
        self.disconnected_callback = disconnected_callback
        self.scripts = list(scripts)
        self.writes = []
        self.is_connected = False
        self.mtu_size = 247
        self.write_error = None
        self.stop_error = None
        self.disconnect_error = None
        self.disconnect_called = False

    async def connect(self):
        self.is_connected = True

    async def start_notify(self, uuid, handler):
        self.handler = handler

    async def write_gatt_char(self, uuid, data, response=None):
        self.writes.append(bytes(data))
        if self.write_error:
            raise self.write_error
        script = self.scripts.pop(0) if self.scripts else []
        for delay, chunk in script:
            asyncio.get_running_loop().call_later(
                delay, lambda data=chunk: asyncio.create_task(self.handler(None, bytearray(data))),
            )

    async def stop_notify(self, uuid):
        if self.stop_error:
            raise self.stop_error

    async def disconnect(self):
        self.disconnect_called = True
        self.is_connected = False
        self.disconnected_callback(self)
        if self.disconnect_error:
            raise self.disconnect_error

    def fire_disconnect(self):
        self.is_connected = False
        self.disconnected_callback(self)


@pytest.fixture
def make_device(monkeypatch):
    async def make(scripts):
        monkeypatch.setattr(ble, 'BleakClient', lambda address, disconnected_callback: FakeBleakClient(
            address, disconnected_callback, scripts,
        ))
        dev = RenacInverterBLE('test-address')
        dev.request_timeout = 0.2
        dev.fragment_timeout = 0.05
        dev.settle_delay = 0.05
        await dev.connect()
        return dev
    return make


def test_fragmented_response_is_reassembled(make_device):
    async def scenario():
        frame = reply(42)
        dev = await make_device([[(0, frame[:2]), (0.01, frame[2:5]), (0.02, frame[5:])]])
        assert await dev.get_min_soc() == 42
        assert dev.stats.requests == 1
    asyncio.run(scenario())


def test_unexpected_frame_is_discarded_and_logged(make_device, caplog):
    async def scenario():
        unexpected = build_write_request(123, 5)
        dev = await make_device([[(0, unexpected), (0.01, reply(42))]])
        assert await dev.get_min_soc() == 42
        assert dev.stats.unexpected_frames == 1
        assert unexpected.hex(' ') in caplog.text
        assert 'MIN_SOC@21018' in caplog.text
    asyncio.run(scenario())


def test_late_reply_after_timeout_does_not_shift_next_read(make_device, caplog):
    async def scenario():
        late = reply(10)
        # The stale FC06 also arrives during B, where the matcher must discard it.
        stale = build_write_request(123, 5)
        dev = await make_device([[(0.22, late), (0.26, stale)], [(0.02, reply(42))]])
        dev.read_attempts = 1
        assert await dev.get_min_soc() is None
        assert await dev.get_min_soc_on_grid() == 42
        assert late.hex(' ') in caplog.text
        assert dev.stats.unexpected_frames == 1
    asyncio.run(scenario())


def test_crc_failure_fails_fast_and_retries(make_device, caplog):
    async def scenario():
        good = reply(42)
        bad = good[:-1] + bytes([good[-1] ^ 1])
        dev = await make_device([[(0, bad)], [(0, good)]])
        started = time.monotonic()
        assert await dev.get_min_soc() == 42
        assert time.monotonic() - started < 0.15
        assert dev.stats.crc_errors == 1
        assert dev.stats.retries == 1
        assert 'MIN_SOC@21018' in caplog.text
        assert bad.hex(' ') in caplog.text
    asyncio.run(scenario())


def test_incomplete_frame_fails_after_fragment_timeout(make_device, caplog):
    async def scenario():
        partial = reply(42)[:4]
        dev = await make_device([[(0, partial)]])
        dev.read_attempts = 1
        started = time.monotonic()
        assert await dev.get_min_soc() is None
        assert time.monotonic() - started < 0.15
        assert dev.stats.incomplete == 1
        assert 'got 4 of 7 bytes' in caplog.text
        assert partial.hex(' ') in caplog.text
    asyncio.run(scenario())


def test_read_exception_response_returns_none_without_retry(make_device, caplog):
    async def scenario():
        dev = await make_device([[(0, crc16(b'\x01\x83\x02'))]])
        assert await dev.get_min_soc() is None
        assert len(dev.client.writes) == 1
        assert dev.stats.exceptions == 1
        assert 'ILLEGAL DATA ADDRESS' in caplog.text
    asyncio.run(scenario())


def test_write_exception_response_returns_false(make_device, caplog):
    async def scenario():
        dev = await make_device([[(0, crc16(b'\x01\x86\x03'))]])
        assert await dev.set_min_soc(20) is False
        assert len(dev.client.writes) == 1
        assert 'ILLEGAL DATA VALUE' in caplog.text
    asyncio.run(scenario())


def test_write_echo_returns_true(make_device):
    async def scenario():
        dev = await make_device([[(0, build_write_request(MIN_SOC['address'], 20))]])
        assert await dev.set_min_soc(20) is True
        assert len(dev.client.writes) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize(('readback', 'expected'), [(20, True), (21, False), (None, None)])
def test_lost_write_echo_is_settled_by_readback(make_device, readback, expected):
    async def scenario():
        dev = await make_device([[], [] if readback is None else [(0, reply(readback))]])
        dev.read_attempts = 1
        assert await dev.set_min_soc(20) is expected
        assert sum(frame[1] == 6 for frame in dev.client.writes) == 1
    asyncio.run(scenario())


def test_timeout_returns_none_after_read_attempts(make_device, caplog):
    async def scenario():
        dev = await make_device([[], []])
        assert await dev.get_min_soc() is None
        assert len(dev.client.writes) == 2
        assert dev.stats.timeouts == 2
        assert 'attempt 1/2' in caplog.text and 'attempt 2/2' in caplog.text
    asyncio.run(scenario())


def test_overview_with_missing_block_returns_partial(make_device):
    async def scenario():
        dev = await make_device([[], [(0, reply(42))], [(0, reply(3))],
                                 [(0, reply(4))], [(0, reply(80))],
                                 [(0, reply(1, EPS_POWER_BLOCK['count']))]])
        dev.read_attempts = 1
        result = await dev.get_power_and_energy_overview()
        assert result['load_power'] == 42
        assert result['battery_soc'] == 80
        assert result['eps_power'] == 1
        assert all(field['name'] not in result for field in TOTAL_ENERGY_BLOCK['fields'])
        assert None not in result.values()
    asyncio.run(scenario())


def test_overview_all_reads_failed_returns_none(make_device):
    async def scenario():
        dev = await make_device([[(0, crc16(b'\x01\x83\x02'))]] * 6)
        assert await dev.get_power_and_energy_overview() is None
    asyncio.run(scenario())


def test_link_loss_fails_pending_request_immediately(make_device):
    async def scenario():
        dev = await make_device([[]])
        asyncio.get_running_loop().call_later(0.01, dev.client.fire_disconnect)
        started = time.monotonic()
        with pytest.raises(ConnectionError):
            await dev.get_min_soc()
        assert time.monotonic() - started < 0.15
        assert not dev.is_connected()
        assert dev.stats.link_losses == 1
        with pytest.raises(ConnectionError):
            await dev.get_min_soc()
    asyncio.run(scenario())


def test_bleak_write_error_raises_connection_error(make_device):
    async def scenario():
        dev = await make_device([])
        dev.client.write_error = BleakError('Service Discovery has not been performed yet')
        with pytest.raises(ConnectionError, match='Service Discovery'):
            await dev.get_min_soc()
        dev.client.fire_disconnect()
        assert dev.stats.link_losses == 1
    asyncio.run(scenario())


def test_disconnect_tolerates_dead_link(make_device):
    async def scenario():
        dev = await make_device([])
        dev.client.stop_error = BleakError('gone')
        dev.client.disconnect_error = BleakError('gone')
        await dev.disconnect()
        assert dev.client.disconnect_called
        assert not dev.is_connected()
        assert dev.stats.link_losses == 0
    asyncio.run(scenario())


def test_cancelled_request_leaves_transport_usable(make_device):
    async def scenario():
        dev = await make_device([[], [(0, reply(42))]])
        task = asyncio.create_task(dev.get_min_soc())
        await asyncio.sleep(0.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await dev.get_min_soc() == 42
    asyncio.run(scenario())


@pytest.mark.parametrize(('value', 'fmt', 'scale', 'wire_value'), [
    (1.6, 'uint16', 1, 2), (-2, 'int16', 1, -2),
])
def test_write_rounds_raw_value_and_reads_back_signed_values(make_device, value, fmt, scale, wire_value):
    async def scenario():
        dev = await make_device([[], [(0, reply(wire_value & 0xFFFF))]])
        register = dict(MIN_SOC, fmt=fmt, scale=scale)
        assert await dev.write_named_register(register, value) is True
        assert dev.client.writes[0][4:6] == (wire_value & 0xFFFF).to_bytes(2, 'big')
    asyncio.run(scenario())


def test_different_write_echo_is_verified_by_readback(make_device):
    async def scenario():
        dev = await make_device([[(0, build_write_request(MIN_SOC['address'], 19))],
                                 [(0, reply(19))]])
        assert await dev.set_min_soc(20) is False
        assert len(dev.client.writes) == 2
    asyncio.run(scenario())


def test_fragment_timeout_resyncs_nonmatching_header(make_device):
    async def scenario():
        # A plausible wrong byte count must not trap the valid frame behind it.
        dev = await make_device([[(0, b'\x01\x03\xfa' + reply(42))]])
        assert await dev.get_min_soc() == 42
        assert dev.stats.incomplete == 1
        assert dev.stats.requests == 1
    asyncio.run(scenario())


def test_bad_crc_on_nonmatching_candidate_does_not_fail_request(make_device):
    async def scenario():
        bad = bytearray(build_write_request(123, 4))
        bad[-1] ^= 1
        dev = await make_device([[(0, bytes(bad) + reply(42))]])
        assert await dev.get_min_soc() == 42
        assert dev.stats.crc_errors == 1
        assert dev.stats.requests == 1
    asyncio.run(scenario())
