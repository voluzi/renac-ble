"""Core BLE helper used by all RENAC devices."""

import asyncio
import logging
from typing import Optional, Callable

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from renac_ble.modbus import (
    build_read_request,
    parse_response,
    parse_block_response,
    build_write_request,
    validate_write_response,
)
from renac_ble.register import Register, RegisterBlock

logger = logging.getLogger(__name__)

NOTIFY_UUID = "0000fec8-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000fed5-0000-1000-8000-00805f9b34fb"


class RenacBLE:
    """Base class providing low level BLE/Modbus communication helpers."""

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
        self._response_event = asyncio.Event()
        self._last_data: Optional[bytes] = None
        self._notification_callback = notification_callback
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Connect to the device and start listening for notifications."""

        self.client = BleakClient(self.address)
        await self.client.connect()
        await self.client.start_notify(self.notify_uuid, self._notify_handler)

    def is_connected(self) -> bool:
        """Return ``True`` if the BLE client is connected."""

        return self.client.is_connected

    async def disconnect(self) -> None:
        """Disconnect and stop notifications if the client is connected."""

        if self.client is not None and self.client.is_connected:
            await self.client.stop_notify(self.notify_uuid)
            await self.client.disconnect()

    async def _notify_handler(
        self, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Handle incoming notifications from the device."""

        # If a request is waiting, handle it
        if not self._response_event.is_set():
            self._last_data = bytes(data)
            self._response_event.set()
        # Otherwise treat it as unsolicited data
        elif self._notification_callback:
            self._notification_callback(bytes(data))

    async def _write_and_get_response(
        self, payload: bytes, timeout: float = 10.0
    ) -> Optional[bytes]:
        """Write a request and wait for the corresponding response."""

        async with self._lock:
            self._last_data = None
            self._response_event.clear()

            await self.client.write_gatt_char(self.write_uuid, payload)
            try:
                await asyncio.wait_for(self._response_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting for response")
                return None
            return self._last_data

    async def read_named_register(self, register: Register) -> float | None:
        """Read and parse a single register defined by :class:`Register`."""

        req = build_read_request(register["address"], register["count"])
        resp = await self._write_and_get_response(req, timeout=15.0)
        if not resp:
            return None
        try:
            # parse response without first 3 bytes and CRC bytes
            return parse_response(
                resp[3:-2], register["fmt"], register["count"], register["scale"]
            )
        except ValueError as e:
            logger.warning(
                "Failed to parse response for register %s: %s", register, e
            )
            return None

    async def write_named_register(self, register: Register, value: int) -> bool | None:
        """Write a value to a register and confirm the response."""

        req = build_write_request(
            register["address"], int(value / register["scale"])
        )
        resp = await self._write_and_get_response(req, timeout=15.0)
        if not resp:
            return None
        # parse response without first 4 bytes and CRC bytes
        return (
            parse_response(
                resp[4:-2], register["fmt"], register["count"], register["scale"]
            )
            == value
        )

    async def read_named_register_block(self, block: RegisterBlock) -> dict | None:
        """Read and parse a :class:`RegisterBlock` from the device."""

        req = build_read_request(block["address"], block["count"])
        resp = await self._write_and_get_response(req, timeout=15.0)
        if not resp:
            return None
        try:
            # parse response without first 3 bytes and CRC bytes
            return parse_block_response(resp[3:-2], block)
        except ValueError as e:
            logger.warning(
                "Failed to parse response for register block %s: %s", block, e
            )
            return None
