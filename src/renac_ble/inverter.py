"""High level API for RENAC inverters."""

import logging
from dataclasses import dataclass
from enum import IntEnum

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


class WorkMode(IntEnum):
    SELF_USE = 0
    FORCE_TIME_USE = 1
    BACKUP = 2
    FEED_IN_FIRST = 3


@dataclass
class GridChargePeriod:
    """Represents a grid charge time period configuration."""

    enabled: bool
    start_hour: int
    start_minute: int
    end_hour: int
    end_minute: int


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

    async def get_work_mode(self) -> WorkMode | None:
        value = await self.read_named_register(WORK_MODE)
        if value is None:
            return None
        try:
            return WorkMode(int(value))
        except ValueError:
            return None

    async def set_work_mode(self, mode: WorkMode) -> bool | None:
        return await self.write_named_register(WORK_MODE, int(mode))

    async def get_max_charge_current(self) -> int | None:
        return await self.read_named_register(MAXIMUM_CHARGE_CURRENT)

    async def set_max_charge_current(self, value: int | None) -> bool | None:
        return await self.write_named_register(MAXIMUM_CHARGE_CURRENT, value)

    async def get_max_discharge_current(self) -> int | None:
        return await self.read_named_register(MAXIMUM_DISCHARGE_CURRENT)

    async def set_max_discharge_current(self, value: int | None) -> bool | None:
        return await self.write_named_register(MAXIMUM_DISCHARGE_CURRENT, value)

    async def get_min_soc(self) -> int | None:
        return await self.read_named_register(MIN_SOC)

    async def set_min_soc(self, value: int | None) -> bool | None:
        return await self.write_named_register(MIN_SOC, value)

    async def get_min_soc_on_grid(self) -> int | None:
        return await self.read_named_register(MIN_SOC_ON_GRID)

    async def set_min_soc_on_grid(self, value: int | None) -> bool | None:
        return await self.write_named_register(MIN_SOC_ON_GRID, value)

    async def get_export_limit(self) -> int | None:
        return await self.read_named_register(EXPORT_LIMIT)

    async def set_export_limit(self, value: int | None) -> bool | None:
        return await self.write_named_register(EXPORT_LIMIT, value)

    async def get_power_limit_percent(self) -> int | None:
        return await self.read_named_register(POWER_LIMIT_PERCENT)

    async def set_power_limit_percent(self, value: int | None) -> bool | None:
        return await self.write_named_register(POWER_LIMIT_PERCENT, value)

    # Force Time Use Mode - Period 1 Grid Charge Settings

    async def get_force_time_period1(self) -> GridChargePeriod | None:
        """Get Force Time Use mode period 1 grid charge settings."""
        enabled = await self.read_named_register(P1_GRID_CHARGE_FLAG)
        start_hour = await self.read_named_register(P1_CHARGE_START_HOUR)
        start_minute = await self.read_named_register(P1_CHARGE_START_MINUTE)
        end_hour = await self.read_named_register(P1_CHARGE_END_HOUR)
        end_minute = await self.read_named_register(P1_CHARGE_END_MINUTE)
        if None in (enabled, start_hour, start_minute, end_hour, end_minute):
            return None
        return GridChargePeriod(
            enabled=bool(int(enabled)),
            start_hour=int(start_hour),
            start_minute=int(start_minute),
            end_hour=int(end_hour),
            end_minute=int(end_minute),
        )

    async def set_force_time_period1(self, period: GridChargePeriod) -> bool:
        """Set Force Time Use mode period 1 grid charge settings."""
        results = [
            await self.write_named_register(P1_GRID_CHARGE_FLAG, int(period.enabled)),
            await self.write_named_register(P1_CHARGE_START_HOUR, period.start_hour),
            await self.write_named_register(P1_CHARGE_START_MINUTE, period.start_minute),
            await self.write_named_register(P1_CHARGE_END_HOUR, period.end_hour),
            await self.write_named_register(P1_CHARGE_END_MINUTE, period.end_minute),
        ]
        return all(r is True for r in results)

    # Force Time Use Mode - Period 2 Grid Charge Settings

    async def get_force_time_period2(self) -> GridChargePeriod | None:
        """Get Force Time Use mode period 2 grid charge settings."""
        enabled = await self.read_named_register(P2_GRID_CHARGE_FLAG)
        start_hour = await self.read_named_register(P2_CHARGE_START_HOUR)
        start_minute = await self.read_named_register(P2_CHARGE_START_MINUTE)
        end_hour = await self.read_named_register(P2_CHARGE_END_HOUR)
        end_minute = await self.read_named_register(P2_CHARGE_END_MINUTE)
        if None in (enabled, start_hour, start_minute, end_hour, end_minute):
            return None
        return GridChargePeriod(
            enabled=bool(int(enabled)),
            start_hour=int(start_hour),
            start_minute=int(start_minute),
            end_hour=int(end_hour),
            end_minute=int(end_minute),
        )

    async def set_force_time_period2(self, period: GridChargePeriod) -> bool:
        """Set Force Time Use mode period 2 grid charge settings."""
        results = [
            await self.write_named_register(P2_GRID_CHARGE_FLAG, int(period.enabled)),
            await self.write_named_register(P2_CHARGE_START_HOUR, period.start_hour),
            await self.write_named_register(P2_CHARGE_START_MINUTE, period.start_minute),
            await self.write_named_register(P2_CHARGE_END_HOUR, period.end_hour),
            await self.write_named_register(P2_CHARGE_END_MINUTE, period.end_minute),
        ]
        return all(r is True for r in results)

    # Backup Mode Grid Charge Settings

    async def get_backup_grid_charge(self) -> GridChargePeriod | None:
        """Get Backup mode grid charge settings."""
        enabled = await self.read_named_register(BACKUP_GRID_CHARGE_FLAG)
        start_hour = await self.read_named_register(BACKUP_CHARGE_START_HOUR)
        start_minute = await self.read_named_register(BACKUP_CHARGE_START_MINUTE)
        end_hour = await self.read_named_register(BACKUP_CHARGE_END_HOUR)
        end_minute = await self.read_named_register(BACKUP_CHARGE_END_MINUTE)
        if None in (enabled, start_hour, start_minute, end_hour, end_minute):
            return None
        return GridChargePeriod(
            enabled=bool(int(enabled)),
            start_hour=int(start_hour),
            start_minute=int(start_minute),
            end_hour=int(end_hour),
            end_minute=int(end_minute),
        )

    async def set_backup_grid_charge(self, period: GridChargePeriod) -> bool:
        """Set Backup mode grid charge settings."""
        results = [
            await self.write_named_register(BACKUP_GRID_CHARGE_FLAG, int(period.enabled)),
            await self.write_named_register(BACKUP_CHARGE_START_HOUR, period.start_hour),
            await self.write_named_register(BACKUP_CHARGE_START_MINUTE, period.start_minute),
            await self.write_named_register(BACKUP_CHARGE_END_HOUR, period.end_hour),
            await self.write_named_register(BACKUP_CHARGE_END_MINUTE, period.end_minute),
        ]
        return all(r is True for r in results)
