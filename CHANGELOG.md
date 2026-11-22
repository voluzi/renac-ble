# Changelog

## 0.2.1

- Fix swapped `load_*_energy` and `input_*_energy` fields. Per protocol V1.00,
  registers 14018/14020 are input energy and 14021/14023 are load energy.

## 0.2.0

- Add N3 HV battery, BMS, inverter temperature and status, fault word, inverter
  AC phase and EPS telemetry.
- Read inverter AC and EPS data in one block and use distinct reply sizes
  for all fast telemetry reads.
- Keep fractional precision for the new measurements and retry failing
  telemetry blocks less often after three consecutive failures.
- Return `Unknown` for unrecognized inverter states.
- Add read and confirmed write support for the inverter bypass relay setting.
- Remove the public `EPS_POWER_BLOCK`, `BATTERY_POWER`, and `BATTERY_SOC`
  constants. Use `INVERTER_AC_EPS_BLOCK` and `BATTERY_BLOCK` from
  `renac_ble.inverter_registers`, or read the same values with
  `get_power_and_energy_overview()`.
