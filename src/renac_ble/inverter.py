"""High level API for RENAC inverters."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from time import monotonic

from renac_ble import inverter_registers
from renac_ble.ble import NOTIFY_UUID, WRITE_UUID, RenacBLE
from renac_ble.inverter_registers import (
    BACKUP_CHARGE_END_HOUR,
    BACKUP_CHARGE_END_MINUTE,
    BACKUP_CHARGE_START_HOUR,
    BACKUP_CHARGE_START_MINUTE,
    BACKUP_GRID_CHARGE_FLAG,
    BATTERY_BLOCK,
    BMS_CELL_BLOCK,
    BYPASS_RELAY_ENABLED,
    EXPORT_LIMIT,
    FAULT_WORD_BLOCK,
    INVERTER_AC_EPS_BLOCK,
    INVERTER_BASIC_INFO,
    INVERTER_STATUS_BLOCK,
    LOAD_POWER,
    MAXIMUM_CHARGE_CURRENT,
    MAXIMUM_DISCHARGE_CURRENT,
    MIN_SOC,
    MIN_SOC_ON_GRID,
    P1_CHARGE_END_HOUR,
    P1_CHARGE_END_MINUTE,
    P1_CHARGE_START_HOUR,
    P1_CHARGE_START_MINUTE,
    P1_GRID_CHARGE_FLAG,
    P2_CHARGE_END_HOUR,
    P2_CHARGE_END_MINUTE,
    P2_CHARGE_START_HOUR,
    P2_CHARGE_START_MINUTE,
    P2_GRID_CHARGE_FLAG,
    POWER_LIMIT_PERCENT,
    PV_INPUT_BLOCK,
    TEMPERATURE_BLOCK,
    TOTAL_ENERGY_BLOCK,
    WORK_MODE,
)
from renac_ble.register import RegisterBlock

logger = logging.getLogger(__name__)

_REGISTER_NAMES = {
    (register["address"], register["count"]): name
    for name, register in vars(inverter_registers).items()
    if isinstance(register, dict) and "address" in register and "count" in register
}


class WorkMode(IntEnum):
    SELF_USE = 0
    FORCE_TIME_USE = 1
    BACKUP = 2
    FEED_IN_FIRST = 3


class InverterState(IntEnum):
    Wait = 0
    Check = 1
    Normal = 2
    Standby = 3
    Fault = 4
    Permanent = 5
    Update = 6
    EpsCheck = 7
    Eps = 8
    SelfTest = 9
    Idle = 10


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

    _register_names = _REGISTER_NAMES
    telemetry_retry_interval_s = 30.0

    def __init__(
        self,
        address: str,
        notification_callback: Callable[[bytes], None] | None = None,
        write_uuid: str = WRITE_UUID,
        notify_uuid: str = NOTIFY_UUID,
    ) -> None:
        super().__init__(address, notification_callback, write_uuid, notify_uuid)
        self._telemetry_failures: dict[int, tuple[int, float | None]] = {}

    async def _read_telemetry_block(self, block: RegisterBlock) -> dict | None:
        address = block["address"]
        failures, retry_at = self._telemetry_failures.get(address, (0, None))
        if retry_at is not None and monotonic() < retry_at:
            return None
        result = await self.read_named_register_block(block)
        if result is not None:
            self._telemetry_failures.pop(address, None)
        else:
            failures = min(failures + 1, 3)
            retry_at = monotonic() + self.telemetry_retry_interval_s if failures == 3 else None
            self._telemetry_failures[address] = (failures, retry_at)
        return result

    async def get_info(self) -> dict | None:
        """Return basic information about the inverter."""

        return await self.read_named_register_block(INVERTER_BASIC_INFO)

    async def get_power_and_energy_overview(self) -> dict | None:
        """Collect an overview of current power and energy values."""

        result = {}
        energy = await self._read_telemetry_block(TOTAL_ENERGY_BLOCK)
        if energy is not None:
            result.update(energy)
        load_power = await self.read_named_register(LOAD_POWER)
        if load_power is not None:
            result["load_power"] = load_power
        pv = await self._read_telemetry_block(PV_INPUT_BLOCK)
        if pv is not None:
            result["pv_power"] = pv["pv1_power"]
        battery = await self._read_telemetry_block(BATTERY_BLOCK)
        if battery is not None:
            result.update(battery)
        phases = await self._read_telemetry_block(INVERTER_AC_EPS_BLOCK)
        if phases is not None:
            result.update(phases)
            for prefix, total in (("inv", "inv_ac_power"), ("eps", "eps_power")):
                result[total] = sum(phases[f"{prefix}_{phase}_power"] for phase in "rst")
        return result or None

    async def get_inverter_status(self) -> dict | None:
        """Return the operating state and charge, discharge and link flags."""
        status = await self._read_telemetry_block(INVERTER_STATUS_BLOCK)
        if status is None:
            return None
        code = status.pop("inverter_state")
        result = {key: bool(value) for key, value in status.items()}
        try:
            state = InverterState(code)
        except ValueError:
            logger.warning("%s: unknown inverter state code %d", self.address, code)
            state = None
        return {
            **result,
            "inverter_state": state.name if state is not None else "Unknown",
            "fault_active": state in (InverterState.Fault, InverterState.Permanent),
        }

    async def get_inverter_diagnostics(self) -> dict | None:
        """Return temperatures, cell data and the 16 raw fault words in register order."""
        result = {}
        for block in (TEMPERATURE_BLOCK, BMS_CELL_BLOCK):
            readings = await self._read_telemetry_block(block)
            if readings is not None:
                result.update(readings)
        faults = await self._read_telemetry_block(FAULT_WORD_BLOCK)
        if faults is not None:
            result["fault_words"] = tuple(faults[f"fault_{index}"] for index in range(1, 17))
        return result or None

    async def get_bypass_relay_enabled(self) -> bool | None:
        value = await self.read_named_register(BYPASS_RELAY_ENABLED)
        return bool(value) if value in (0, 1) else None

    async def set_bypass_relay_enabled(self, enabled: bool) -> bool | None:
        if not isinstance(enabled, bool):
            return False
        return await self.write_named_register(BYPASS_RELAY_ENABLED, int(enabled))

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
