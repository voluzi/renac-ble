"""High level API for RENAC inverters."""

import logging

from bleak.backends.characteristic import BleakGATTCharacteristic

from renac_ble.ble import RenacBLE
from renac_ble.modbus import validate_crc
from renac_ble.inverter_registers import *

logger = logging.getLogger(__name__)

OVERVIEW_REGISTERS = {
    "load_power": LOAD_POWER,
    "pv_power": PV1_POWER,
    "battery_power": BATTERY_POWER,
    "battery_soc": BATTERY_SOC,
}


class RenacInverterBLE(RenacBLE):
    """Client for interacting with RENAC hybrid inverters."""

    def __init__(self, address: str) -> None:
        super().__init__(address)

    async def _notify_handler(
        self, sender: BleakGATTCharacteristic, data: bytearray
    ) -> None:
        """Validate CRC before delegating to the base handler."""

        if not validate_crc(data):
            logger.warning("CRC check failed in inverter response")
            return
        await super()._notify_handler(sender, data)

    async def get_info(self) -> dict | None:
        """Return basic information about the inverter."""

        return await self.read_named_register_block(INVERTER_BASIC_INFO)

    async def get_power_and_energy_overview(self) -> dict | None:
        """Collect an overview of current power and energy values."""

        result = await self.read_named_register_block(TOTAL_ENERGY_BLOCK)
        for name, register in OVERVIEW_REGISTERS.items():
            result[name] = await self.read_named_register(register)
        eps_data = await self.read_named_register_block(EPS_POWER_BLOCK)
        result["eps_power"] = (
            eps_data["eps_r_power"]
            + eps_data["eps_s_power"]
            + eps_data["eps_t_power"]
        )
        return result

    async def get_max_charge_current(self) -> int | None:
        return await self.read_named_register(MAXIMUM_CHARGE_CURRENT)

    async def set_max_charge_current(self, value: int | None) -> bool:
        return await self.write_named_register(MAXIMUM_CHARGE_CURRENT, value)

    async def get_max_discharge_current(self) -> int | None:
        return await self.read_named_register(MAXIMUM_DISCHARGE_CURRENT)

    async def set_max_discharge_current(self, value: int | None) -> bool:
        return await self.write_named_register(MAXIMUM_DISCHARGE_CURRENT, value)

    async def get_min_soc(self) -> int | None:
        return await self.read_named_register(MIN_SOC)

    async def set_min_soc(self, value: int | None) -> bool:
        return await self.write_named_register(MIN_SOC, value)

    async def get_min_soc_on_grid(self) -> int | None:
        return await self.read_named_register(MIN_SOC_ON_GRID)

    async def set_min_soc_on_grid(self, value: int | None) -> bool:
        return await self.write_named_register(MIN_SOC_ON_GRID, value)

    async def get_export_limit(self) -> int | None:
        return await self.read_named_register(EXPORT_LIMIT)

    async def set_export_limit(self, value: int | None) -> bool:
        return await self.write_named_register(EXPORT_LIMIT, value)

    async def get_power_limit_percent(self) -> int | None:
        return await self.read_named_register(POWER_LIMIT_PERCENT)

    async def set_power_limit_percent(self, value: int | None) -> bool:
        return await self.write_named_register(POWER_LIMIT_PERCENT, value)
