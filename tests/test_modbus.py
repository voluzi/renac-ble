import pytest

from renac_ble.modbus import (
    INVALID, BadCrc, Frame, Garbage, ModbusFrameBuffer, crc16, frame_length,
)


@pytest.mark.parametrize(('header', 'length'), [
    (b'', None), (b'\x01', None), (b'\x01\x03', None),
    (b'\x01\x03\x02', 7), (b'\x01\x06', 8), (b'\x01\x10', 8),
    (b'\x01\x83', 5), (b'\x01\x86', 5), (b'\x01\x90', 5),
    (b'\x02\x03', INVALID), (b'\x01\x04', INVALID),
    (b'\x01\x03\x00', INVALID), (b'\x01\x03\x03', INVALID),
    (b'\x01\x03\xfc', INVALID),
])
def test_frame_length_by_function_code(header, length):
    assert frame_length(header) == length


def test_buffer_reassembles_fragmented_frame():
    frame = crc16(b'\x01\x03\x36' + bytes(range(54)))
    buffer = ModbusFrameBuffer()
    assert buffer.feed(frame[:2]) == []
    assert buffer.feed(frame[2:30]) == []
    assert buffer.pending == frame[:30]
    assert buffer.feed(frame[30:]) == [Frame(frame)]
    assert buffer.pending == b''


def test_buffer_extracts_two_frames_from_one_notification():
    first = crc16(b'\x01\x03\x02\x00\x14')
    second = crc16(b'\x01\x86\x03')
    assert ModbusFrameBuffer().feed(first + second) == [Frame(first), Frame(second)]


def test_buffer_resyncs_after_garbage_prefix():
    frame = crc16(b'\x01\x03\x02\x00\x14')
    assert ModbusFrameBuffer().feed(b'\xff\x01\x03\xfd' + frame) == [
        Garbage(b'\xff\x01\x03\xfd'), Frame(frame),
    ]


@pytest.mark.parametrize('prefix', [b'', b'\xff\xfe'])
def test_buffer_reports_crc_failure_and_resyncs(prefix):
    frame = crc16(b'\x01\x03\x02\x00\x14')
    corrupt = frame[:-1] + bytes([frame[-1] ^ 1])
    events = ModbusFrameBuffer().feed(prefix + corrupt + frame)
    if prefix:
        assert events[:2] == [Garbage(prefix), BadCrc(corrupt)]
    else:
        assert events[0] == BadCrc(corrupt)
    assert events[-1] == Frame(frame)
