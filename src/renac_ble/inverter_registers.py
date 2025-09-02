"""Register definitions for RENAC inverters."""

from renac_ble.register import Register, RegisterBlock

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

EPS_POWER_BLOCK: RegisterBlock = {
    "address": 11094,
    "count": 3,  # 1 register per phase
    "fields": [
        {
            "name": "eps_r_power",
            "offset": 0,
            "length": 2,
            "fmt": "int16",
            "scale": 1,
            "unit": "W"
        },
        {
            "name": "eps_s_power",
            "offset": 2,
            "length": 2,
            "fmt": "int16",
            "scale": 1,
            "unit": "W"
        },
        {
            "name": "eps_t_power",
            "offset": 4,
            "length": 2,
            "fmt": "int16",
            "scale": 1,
            "unit": "W"
        },
    ]
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

BATTERY_POWER: Register = {
    "address": 11022,
    "count": 1,
    "fmt": "int16",
    "scale": 1,
    "unit": "W",
}

BATTERY_SOC: Register = {
    "address": 11026,
    "count": 1,
    "fmt": "uint16",
    "scale": 1,
    "unit": "%",
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
