"""Register definitions for RENAC inverters."""

from typing import Literal

from renac_ble.register import Register, RegisterBlock, RegisterField

# https://www.photovoltaikforum.com/core/file-download/380139/

INVERTER_BASIC_INFO: RegisterBlock = {
    "address": 10000,
    "count": 38,
    "fields": [
        {"name": "model", "offset": 0, "length": 32, "fmt": "ascii", "scale": 1, "unit": ""},
        {"name": "sn", "offset": 32, "length": 32, "fmt": "ascii", "scale": 1, "unit": ""},
        {"name": "hmi_version", "offset": 70, "length": 2, "fmt": "uint16", "scale": 0.01, "unit": ""},
        {"name": "invm_version", "offset": 76, "length": 2, "fmt": "uint16", "scale": 0.01, "unit": ""},
        {"name": "invs_version", "offset": 78, "length": 2, "fmt": "uint16", "scale": 0.01, "unit": ""},
    ]
}

PV_INPUT_BLOCK: RegisterBlock = {
    "address": 11000,
    "count": 6,  # 6 registers total (each 2 bytes)
    "fields": [
        {
            "name": "pv1_voltage",
            "offset": 0,
            "length": 2,
            "fmt": "int16",
            "scale": 0.1,
            "unit": "V",
        },
        {
            "name": "pv1_current",
            "offset": 2,
            "length": 2,
            "fmt": "int16",
            "scale": 0.1,
            "unit": "A",
        },
        {
            "name": "pv1_power",
            "offset": 4,
            "length": 2,
            "fmt": "int16",
            "scale": 1.0,
            "unit": "W",
        },
        {
            "name": "pv2_voltage",
            "offset": 6,
            "length": 2,
            "fmt": "int16",
            "scale": 0.1,
            "unit": "V",
        },
        {
            "name": "pv2_current",
            "offset": 8,
            "length": 2,
            "fmt": "int16",
            "scale": 0.1,
            "unit": "A",
        },
        {
            "name": "pv2_power",
            "offset": 10,
            "length": 2,
            "fmt": "int16",
            "scale": 1.0,
            "unit": "W",
        },
    ],
}


def _telemetry_block(
    address: int,
    *fields: tuple[str, Literal["int16", "uint16"], float, str] | None,
) -> RegisterBlock:
    decoded: list[RegisterField] = []
    for index, field in enumerate(fields):
        if field is not None:
            name, fmt, scale, unit = field
            decoded.append(
                {"name": name, "offset": 2 * index, "length": 2, "fmt": fmt, "scale": scale, "unit": unit}
            )
    return {"address": address, "count": len(fields), "fields": decoded, "precision": 3}


TEMPERATURE_BLOCK = _telemetry_block(
    11016,
    ("internal_temp", "int16", 0.1, "°C"),
    ("charger_temp", "int16", 0.1, "°C"),
    ("boost_temp", "int16", 0.1, "°C"),
    ("inverter_temp", "int16", 0.1, "°C"),
)

BATTERY_BLOCK = _telemetry_block(
    11020,
    ("battery_voltage", "int16", 0.1, "V"),
    ("battery_current", "int16", 0.1, "A"),
    ("battery_power", "int16", 1, "W"),
    ("bms_voltage", "int16", 0.1, "V"),
    ("bms_current", "int16", 0.1, "A"),
    ("bms_temp", "int16", 0.1, "°C"),
    ("battery_soc", "uint16", 1, "%"),
    ("bms_soh", "uint16", 1, "%"),
)

BMS_CELL_BLOCK = _telemetry_block(
    11030,
    ("bms_max_charge_a", "int16", 0.1, "A"),
    ("bms_max_discharge_a", "int16", 0.1, "A"),
    ("max_cell_v", "int16", 0.001, "V"),
    ("min_cell_v", "int16", 0.001, "V"),
    ("max_cell_v_no", "uint16", 1, ""),
    ("min_cell_v_no", "uint16", 1, ""),
    ("max_cell_t", "int16", 0.1, "°C"),
    ("min_cell_t", "int16", 0.1, "°C"),
    ("max_cell_t_no", "uint16", 1, ""),
    ("min_cell_t_no", "uint16", 1, ""),
    ("bms_basic_status", "uint16", 1, ""),
    ("bms_cycles", "uint16", 1, ""),
)

INVERTER_STATUS_BLOCK = _telemetry_block(
    11050,
    ("forbid_charge", "uint16", 1, ""),
    ("forbid_discharge", "uint16", 1, ""),
    None, None, None, None, None,
    ("inverter_state", "uint16", 1, ""),
    ("bms_connected", "uint16", 1, ""),
    ("meter1_connected", "uint16", 1, ""),
)

FAULT_WORD_BLOCK = _telemetry_block(
    11060, *((f"fault_{index}", "uint16", 1, "") for index in range(1, 17)),
)

INVERTER_AC_EPS_BLOCK = _telemetry_block(
    11079,
    ("inv_r_current", "int16", 0.1, "A"),
    ("inv_s_current", "int16", 0.1, "A"),
    ("inv_t_current", "int16", 0.1, "A"),
    ("inv_r_power", "int16", 1, "W"),
    ("inv_s_power", "int16", 1, "W"),
    ("inv_t_power", "int16", 1, "W"),
    None, None, None,
    ("eps_r_voltage", "uint16", 0.1, "V"),
    ("eps_s_voltage", "uint16", 0.1, "V"),
    ("eps_t_voltage", "uint16", 0.1, "V"),
    ("eps_r_current", "int16", 0.1, "A"),
    ("eps_s_current", "int16", 0.1, "A"),
    ("eps_t_current", "int16", 0.1, "A"),
    ("eps_r_power", "int16", 1, "W"),
    ("eps_s_power", "int16", 1, "W"),
    ("eps_t_power", "int16", 1, "W"),
    ("eps_frequency", "uint16", 0.01, "Hz"),
)

BYPASS_RELAY_ENABLED: Register = {
    "address": 20109,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "",
}

TOTAL_ENERGY_BLOCK: RegisterBlock = {
    "address": 14000,
    "count": 27,
    "fields": [
        {"name": "pv_total_energy", "offset": 0, "length": 4, "fmt": "uint32", "scale": 0.1, "unit": "kWh"},
        {"name": "pv_today_energy", "offset": 4, "length": 2, "fmt": "uint16", "scale": 0.1, "unit": "kWh"},
        {"name": "battery_total_charge_energy", "offset": 6, "length": 4, "fmt": "uint32", "scale": 0.1, "unit": "kWh"},
        {"name": "battery_today_charge_energy", "offset": 10, "length": 2, "fmt": "uint16", "scale": 0.1,
         "unit": "kWh"},
        {"name": "battery_total_discharge_energy", "offset": 12, "length": 4, "fmt": "uint32", "scale": 0.1,
         "unit": "kWh"},
        {"name": "battery_today_discharge_energy", "offset": 16, "length": 2, "fmt": "uint16", "scale": 0.1,
         "unit": "kWh"},
        {"name": "feedin_total_energy", "offset": 18, "length": 4, "fmt": "uint32", "scale": 0.1, "unit": "kWh"},
        {"name": "feedin_today_energy", "offset": 22, "length": 2, "fmt": "uint16", "scale": 0.1, "unit": "kWh"},
        {"name": "consumption_total_energy", "offset": 24, "length": 4, "fmt": "uint32", "scale": 0.1, "unit": "kWh"},
        {"name": "consumption_today_energy", "offset": 28, "length": 2, "fmt": "uint16", "scale": 0.1, "unit": "kWh"},
        {"name": "output_total_energy", "offset": 30, "length": 4, "fmt": "uint32", "scale": 0.1, "unit": "kWh"},
        {"name": "output_today_energy", "offset": 34, "length": 2, "fmt": "uint16", "scale": 0.1, "unit": "kWh"},
        {"name": "load_total_energy", "offset": 36, "length": 4, "fmt": "uint32", "scale": 0.1, "unit": "kWh"},
        {"name": "load_today_energy", "offset": 40, "length": 2, "fmt": "uint16", "scale": 0.1, "unit": "kWh"},
        {"name": "input_total_energy", "offset": 42, "length": 4, "fmt": "uint32", "scale": 0.1, "unit": "kWh"},
        {"name": "input_today_energy", "offset": 46, "length": 2, "fmt": "uint16", "scale": 0.1, "unit": "kWh"},
        {"name": "eps_total_energy", "offset": 48, "length": 4, "fmt": "uint32", "scale": 0.1, "unit": "kWh"},
        {"name": "eps_today_energy", "offset": 52, "length": 2, "fmt": "uint16", "scale": 0.1, "unit": "kWh"},
    ],
}

METER1_POWER_BLOCK: RegisterBlock = {
    "address": 11098,
    "count": 4,  # 4 consecutive registers: 11098 to 11101
    "fields": [
        {"name": "meter1_r_power", "offset": 0, "length": 2, "fmt": "int16", "scale": 1.0, "unit": "W"},
        {"name": "meter1_s_power", "offset": 2, "length": 2, "fmt": "int16", "scale": 1.0, "unit": "W"},
        {"name": "meter1_t_power", "offset": 4, "length": 2, "fmt": "int16", "scale": 1.0, "unit": "W"},
        {"name": "meter1_total_power", "offset": 6, "length": 2, "fmt": "int16", "scale": 1.0, "unit": "W"},
    ]
}

GRID_VOLTAGE_BLOCK: RegisterBlock = {
    "address": 11076,
    "count": 3,
    "fields": [
        {"name": "grid_voltage_r", "offset": 0, "length": 2, "fmt": "uint16", "scale": 0.1, "unit": "V"},
        {"name": "grid_voltage_s", "offset": 2, "length": 2, "fmt": "uint16", "scale": 0.1, "unit": "V"},
        {"name": "grid_voltage_t", "offset": 4, "length": 2, "fmt": "uint16", "scale": 0.1, "unit": "V"},
    ],
}

LOAD_POWER: Register = {
    "address": 11113,
    "count": 1,
    "fmt": "int16",
    "scale": 1,
    "unit": "W",
}

LOAD_TOTAL_ENERGY: Register = {
    "address": 14012,
    "count": 2,
    "fmt": "uint32",
    "scale": 0.1,
    "unit": "kWh",
}

PV1_POWER: Register = {
    "address": 11002,
    "count": 1,
    "fmt": "int16",
    "scale": 1,
    "unit": "W",
}

PV1_TOTAL_ENERGY: Register = {
    "address": 14000,
    "count": 2,
    "fmt": "uint32",
    "scale": 0.1,
    "unit": "kWh",
}

BATTERY_TOTAL_CHARGE_ENERGY: Register = {
    "address": 14003,
    "count": 2,
    "fmt": "uint32",
    "scale": 0.1,
    "unit": "kWh",
}

BATTERY_TOTAL_DISCHARGE_ENERGY: Register = {
    "address": 14006,
    "count": 2,
    "fmt": "uint32",
    "scale": 0.1,
    "unit": "kWh",
}

# 0: Self use
# 1: ForceTime Use
# 2: Back up
# 3: Feed-in First
WORK_MODE: Register = {
    "address": 21000,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "",
}

MAXIMUM_CHARGE_CURRENT: Register = {
    "address": 21016,
    "count": 1,
    "fmt": "uint16",
    "scale": 0.1,
    "unit": "A",
}

MAXIMUM_DISCHARGE_CURRENT: Register = {
    "address": 21017,
    "count": 1,
    "fmt": "uint16",
    "scale": 0.1,
    "unit": "A",
}

MIN_SOC: Register = {
    "address": 21018,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "%",
}

MIN_SOC_ON_GRID: Register = {
    "address": 21019,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "%",
}

EXPORT_LIMIT: Register = {
    "address": 21020,
    "count": 1,
    "fmt": "uint16",
    "scale": 10,
    "unit": "W",
}

POWER_LIMIT_PERCENT: Register = {
    "address": 21021,
    "count": 1,
    "fmt": "int16",
    "scale": 1,
    "unit": "Pn/100",
}

# Force Time Use Mode - Period 1 Grid Charge Settings
P1_GRID_CHARGE_FLAG: Register = {
    "address": 21001,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "",
}

P1_CHARGE_START_HOUR: Register = {
    "address": 21002,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "",
}

P1_CHARGE_START_MINUTE: Register = {
    "address": 21003,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "",
}

P1_CHARGE_END_HOUR: Register = {
    "address": 21004,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "",
}

P1_CHARGE_END_MINUTE: Register = {
    "address": 21005,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "",
}

# Force Time Use Mode - Period 2 Grid Charge Settings
P2_GRID_CHARGE_FLAG: Register = {
    "address": 21006,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "",
}

P2_CHARGE_START_HOUR: Register = {
    "address": 21007,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "",
}

P2_CHARGE_START_MINUTE: Register = {
    "address": 21008,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "",
}

P2_CHARGE_END_HOUR: Register = {
    "address": 21009,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "",
}

P2_CHARGE_END_MINUTE: Register = {
    "address": 21010,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "",
}

# Backup Mode Grid Charge Settings
BACKUP_GRID_CHARGE_FLAG: Register = {
    "address": 21011,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "",
}

BACKUP_CHARGE_START_HOUR: Register = {
    "address": 21012,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "",
}

BACKUP_CHARGE_START_MINUTE: Register = {
    "address": 21013,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "",
}

BACKUP_CHARGE_END_HOUR: Register = {
    "address": 21014,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "",
}

BACKUP_CHARGE_END_MINUTE: Register = {
    "address": 21015,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "",
}
