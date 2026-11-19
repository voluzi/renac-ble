import asyncio
import struct
import time

import pytest
from bleak.exc import BleakError

from renac_ble import ble
from renac_ble.inverter import RenacInverterBLE
from renac_ble.inverter_registers import MIN_SOC, TOTAL_ENERGY_BLOCK
from renac_ble.modbus import (
    build_read_request, build_write_multiple_request, build_write_request, crc16,
)
from renac_ble.wallbox import WALLBOX_PREFIX, CHARGER_COMMAND_ADDRESS, RenacWallboxBLE


def reply(value=20, count=1):
    return crc16(bytes([1, 3, count * 2]) + value.to_bytes(count * 2, 'big'))


def words(*values):
    payload = struct.pack(f'>{len(values)}H', *(value & 0xffff for value in values))
    return crc16(bytes([1, 3, len(payload)]) + payload)


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
    async def make(scripts, device_class=RenacInverterBLE):
        monkeypatch.setattr(ble, 'BleakClient', lambda address, disconnected_callback: FakeBleakClient(
            address, disconnected_callback, scripts,
        ))
        dev = device_class('test-address')
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
        dev = await make_device([[(0.25, late)], [(0, stale), (0.05, reply(42))]])
        dev.settle_delay = 0.15
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
        assert time.monotonic() - started < dev.request_timeout
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
        assert time.monotonic() - started < dev.request_timeout
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
                                 [(0, words(4001, -23, 4, 4012, -37, -54, 80, 97))],
                                 [(0, words(-71, 82, -93, -200, 500, 13))],
                                 [(0, words(2301, 2312, 2323, -14, 20, -21, -3, 9, -5, 4999))]])
        dev.read_attempts = 1
        result = await dev.get_power_and_energy_overview()
        assert result['load_power'] == 42
        assert result['battery_soc'] == 80
        assert result['battery_power'] == 4
        assert result['eps_power'] == 1
        expected = {
            'battery_voltage': 400.1, 'battery_current': -2.3, 'bms_voltage': 401.2,
            'bms_current': -3.7, 'bms_temp': -5.4, 'bms_soh': 97, 'inv_r_current': -7.1,
            'inv_s_current': 8.2, 'inv_t_current': -9.3, 'inv_r_power': -200, 'inv_s_power': 500,
            'inv_t_power': 13, 'inv_ac_power': 313, 'eps_r_voltage': 230.1, 'eps_s_voltage': 231.2,
            'eps_t_voltage': 232.3, 'eps_r_current': -1.4, 'eps_s_current': 2, 'eps_t_current': -2.1,
            'eps_r_power': -3, 'eps_s_power': 9, 'eps_t_power': -5, 'eps_frequency': 49.99,
        }
        assert expected.items() <= result.items()
        assert all(field['name'] not in result for field in TOTAL_ENERGY_BLOCK['fields'])
        assert None not in result.values()
        assert dev.client.writes == [
            build_read_request(address, count)
            for address, count in [(14000, 27), (11113, 1), (11002, 1), (11020, 8), (11079, 6), (11088, 10)]
        ]
    asyncio.run(scenario())


def test_overview_all_reads_failed_returns_none(make_device):
    async def scenario():
        dev = await make_device([[(0, crc16(b'\x01\x83\x02'))]] * 6)
        assert await dev.get_power_and_energy_overview() is None
    asyncio.run(scenario())


def test_inverter_diagnostics_decode_temperatures_cells_and_fault_words(make_device):
    async def scenario():
        dev = await make_device([
            [(0, words(-123, 234, -17, 459))],
            [(0, words(-155, 237, 3421, 3128, 7, 8, 527, -89, 10, 11, 0x8000, 402))],
            [(0, words(0, 0, 0, 0, 0, 0, 24, 0, 0, 0, 0, 0, 0, 0, 0, 0x8001))],
        ])
        result = await dev.get_inverter_diagnostics()
        assert result == {
            'internal_temp': -12.3, 'charger_temp': 23.4, 'boost_temp': -1.7, 'inverter_temp': 45.9,
            'bms_max_charge_a': -15.5, 'bms_max_discharge_a': 23.7, 'max_cell_v': 3.421,
            'min_cell_v': 3.128, 'max_cell_v_no': 7, 'min_cell_v_no': 8, 'max_cell_t': 52.7,
            'min_cell_t': -8.9, 'max_cell_t_no': 10, 'min_cell_t_no': 11,
            'bms_basic_status': 0x8000, 'bms_cycles': 402,
            'fault_words': (0, 0, 0, 0, 0, 0, 24, 0, 0, 0, 0, 0, 0, 0, 0, 0x8001),
        }
        assert dev.client.writes == [
            build_read_request(11016, 4), build_read_request(11030, 12), build_read_request(11060, 16),
        ]
    asyncio.run(scenario())


@pytest.mark.parametrize(('code', 'label'), list(enumerate((
    'Wait', 'Check', 'Normal', 'Standby', 'Fault', 'Permanent',
    'Update', 'EpsCheck', 'Eps', 'SelfTest', 'Idle', None,
))))
def test_inverter_operating_state_and_fault_active(make_device, code, label):
    async def scenario():
        dev = await make_device([[(0, words(1, 0, 96, 4, 24, 300, 50, code, 1, 0))]])
        result = await dev.get_inverter_status()
        assert result == {
            'forbid_charge': True, 'forbid_discharge': False, 'bms_connected': True,
            'meter1_connected': False,
            **({'inverter_state': label, 'fault_active': code in (4, 5)} if label else {}),
        }
        assert dev.client.writes == [build_read_request(11050, 10)]
    asyncio.run(scenario())


def test_bypass_relay_uses_single_register_read_and_verified_write(make_device):
    async def scenario():
        dev = await make_device([
            [(0, reply(0))], [(0, build_write_request(20109, 1))],
            [(0, reply(1))], [], [(0, reply(1))],
        ])
        assert await dev.get_bypass_relay_enabled() is False
        assert await dev.set_bypass_relay_enabled(True) is True
        assert await dev.get_bypass_relay_enabled() is True
        assert await dev.set_bypass_relay_enabled(False) is False
        assert dev.client.writes == [
            build_read_request(20109, 1), build_write_request(20109, 1),
            build_read_request(20109, 1), build_write_request(20109, 0),
            build_read_request(20109, 1),
        ]
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


def test_different_write_echo_is_verified_by_readback(make_device, caplog):
    async def scenario():
        dev = await make_device([[(0, build_write_request(MIN_SOC['address'], 19))],
                                 [(0, reply(19))]])
        assert await dev.set_min_soc(20) is False
        assert len(dev.client.writes) == 2
        assert len(caplog.records) == 1
        assert 'echo differs, readback 19 (expected 20)' in caplog.text
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


@pytest.mark.parametrize(('command', 'stale'), [('start_charging', 2), ('stop_charging', 1)])
def test_wallbox_ignores_opposite_command_echo(make_device, command, stale):
    async def scenario():
        value = 1 if command == 'start_charging' else 2
        opposite = WALLBOX_PREFIX + build_write_request(CHARGER_COMMAND_ADDRESS, stale)
        expected = WALLBOX_PREFIX + build_write_request(CHARGER_COMMAND_ADDRESS, value)
        dev = await make_device([[(0, opposite), (0.05, expected)]], RenacWallboxBLE)
        assert await getattr(dev, command)() is True
        assert dev.client.writes == [expected]
        assert dev.stats.unexpected_frames == 1
    asyncio.run(scenario())


def test_wallbox_command_exception_settles_request(make_device):
    async def scenario():
        exception = WALLBOX_PREFIX + crc16(b'\x01\x86\x03')
        dev = await make_device([[(0, exception)]], RenacWallboxBLE)
        assert await dev.stop_charging() is False
        assert len(dev.client.writes) == 1
        assert dev.stats.exceptions == 1
        assert dev.stats.timeouts == 0
    asyncio.run(scenario())


@pytest.mark.parametrize('function', [6, 16])
@pytest.mark.parametrize('size', [2, 3])
def test_short_write_echo_fails_at_fragment_timeout(make_device, function, size):
    async def scenario():
        request = (build_write_request(MIN_SOC['address'], 20) if function == 6
                   else build_write_multiple_request(MIN_SOC['address'], b'\x00\x14'))
        dev = await make_device([[(0, request[:size])]])
        started = time.monotonic()
        assert await dev._transact(request) is None
        assert time.monotonic() - started < dev.request_timeout
        assert dev.stats.incomplete == 1
        assert dev.stats.timeouts == 0
    asyncio.run(scenario())
