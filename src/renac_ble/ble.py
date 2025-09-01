import asyncio
from typing import Optional, Callable
from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from renac_ble.modbus import build_read_request, parse_response, parse_block_response, build_write_request, \
    validate_write_response
from renac_ble.register import Register, RegisterBlock

NOTIFY_UUID = "0000fec8-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000fed5-0000-1000-8000-00805f9b34fb"


class RenacBLE:
    def __init__(self, address: str, notification_callback: Optional[Callable[[bytes], None]] = None,
                 write_uuid=WRITE_UUID, notify_uuid=NOTIFY_UUID):
        self.write_uuid = write_uuid
        self.notify_uuid = notify_uuid
        self.address = address
        self.client: Optional[BleakClient] = None
        self._response_event = asyncio.Event()
        self._last_data: Optional[bytes] = None
        self._notification_callback = notification_callback
        self._lock = asyncio.Lock()

    async def connect(self):
        self.client = BleakClient(self.address)
        await self.client.connect()
        await self.client.start_notify(self.notify_uuid, self._notify_handler)

    def is_connected(self) -> bool:
        return self.client.is_connected

    async def disconnect(self):
        if self.client is not None and self.client.is_connected:
            await self.client.stop_notify(self.notify_uuid)
            await self.client.disconnect()

    async def _notify_handler(self, sender: BleakGATTCharacteristic, data: bytearray):
        # If a request is waiting, handle it
        if not self._response_event.is_set():
            self._last_data = bytes(data)
            self._response_event.set()
        # Otherwise treat it as unsolicited data
        elif self._notification_callback:
            self._notification_callback(bytes(data))

    async def _write_and_get_response(self, payload: bytes, timeout=10.0) -> Optional[bytes]:
        async with self._lock:
            self._last_data = None
            self._response_event.clear()

            await self.client.write_gatt_char(self.write_uuid, payload)
            try:
                await asyncio.wait_for(self._response_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                print("Timed out waiting for response")
                return None
            return self._last_data

    async def read_named_register(self, register: Register) -> float | None:
        req = build_read_request(register['address'], register['count'])
        resp = await self._write_and_get_response(req, timeout=15.0)
        if not resp:
            return None
        try:
            # parse response without first 3 bytes and CRC bytes
            return parse_response(resp[3:-2], register['fmt'], register['count'], register['scale'])
        except ValueError as e:
            print(f"⚠️  Failed to parse response for register {register}: {e}")
            return None

    async def write_named_register(self, register: Register, value: int) -> bool | None:
        req = build_write_request(register['address'], int(value / register['scale']))
        resp = await self._write_and_get_response(req, timeout=15.0)
        if not resp:
            return None
        # parse response without first 4 bytes and CRC bytes
        return parse_response(resp[4:-2], register['fmt'], register['count'], register['scale']) == value

    async def read_named_register_block(self, block: RegisterBlock) -> dict | None:
        req = build_read_request(block['address'], block['count'])
        resp = await self._write_and_get_response(req, timeout=15.0)
        if not resp:
            return None
        try:
            # parse response without first 3 bytes and CRC bytes
            return parse_block_response(resp[3:-2], block)
        except ValueError as e:
            print(f"⚠️  Failed to parse response for register block {block}: {e}")
            return None
