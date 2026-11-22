from renac_ble.inverter_registers import TOTAL_ENERGY_BLOCK

# Register addresses from the RENAC N3 HV Modbus Protocol V1.00.
EXPECTED = {
    "pv_total_energy": 14000,
    "pv_today_energy": 14002,
    "battery_total_charge_energy": 14003,
    "battery_today_charge_energy": 14005,
    "battery_total_discharge_energy": 14006,
    "battery_today_discharge_energy": 14008,
    "feedin_total_energy": 14009,
    "feedin_today_energy": 14011,
    "consumption_total_energy": 14012,
    "consumption_today_energy": 14014,
    "output_total_energy": 14015,
    "output_today_energy": 14017,
    "input_total_energy": 14018,
    "input_today_energy": 14020,
    "load_total_energy": 14021,
    "load_today_energy": 14023,
    "eps_total_energy": 14024,
    "eps_today_energy": 14026,
}


def test_total_energy_fields_match_protocol_addresses():
    base = TOTAL_ENERGY_BLOCK["address"]
    actual = {
        field["name"]: base + field["offset"] // 2
        for field in TOTAL_ENERGY_BLOCK["fields"]
    }
    assert actual == EXPECTED
