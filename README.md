# renac-ble

**BLE communication library for RENAC inverters and wallboxes.**

This package provides a low-level Python API to connect to RENAC devices over Bluetooth Low Energy (BLE), parse telemetry, and send control commands.  
It is designed to be used directly or as a backend for higher-level integrations such as [renac-ha-mqtt](https://github.com/voluzi/renac-ha-mqtt).

---

## ✨ Features
- Discover and connect to RENAC devices over BLE
- Parse device information and runtime telemetry
- Subscribe to notifications (real-time updates)
- Send control commands (charge/discharge limits, SoC settings, export limits, …)
- Async/await interface based on [bleak](https://github.com/hbldh/bleak)

---

## 📦 Installation

```bash
pip install "git+https://github.com/voluzi/renac-ble.git@main"
```

---

## 🚀 Usage

### Example
```python
import asyncio
from renac_ble import RenacInverterBLE, RenacWallboxBLE

async def main():
    inverter = RenacInverterBLE("28:9C:6E:92:7C:F6")
    wallbox = RenacWallboxBLE("E8:FD:F8:D4:A1:75")

    await inverter.connect()
    print("⚡️ Connected to inverter")

    info = await inverter.get_info()
    print("Inverter info:", info)

    telemetry = await inverter.get_power_and_energy_overview()
    print("Telemetry:", telemetry)

    await wallbox.connect()
    print("⚡️ Connected to wallbox")

    print("Wallbox settings:", await wallbox.get_basic_settings())
    await wallbox.set_max_output_current(16)  # amperes, 6–32
    await wallbox.stop_charging()  # some cars only resume after re-plugging

    await inverter.disconnect()
    await wallbox.disconnect()

asyncio.run(main())
```

### N3 HV inverter telemetry and bypass relay

- `get_power_and_energy_overview()` includes battery and BMS electrical readings,
  BMS temperature and state of health, inverter AC phase currents and powers,
  and EPS phase voltages, currents, powers and frequency. The inverter AC and
  EPS power totals are calculated from the three phase powers.
- `get_inverter_status()` returns the inverter state label and boolean charge,
  discharge and connection flags. `fault_active` is true only in `Fault` or
  `Permanent`.
- `get_inverter_diagnostics()` returns inverter temperatures, BMS cell
  measurements and indexes, basic status, cycle count, and the 16 unsigned
  `fault_words` in register order. Poll this less often than the overview.
- `get_bypass_relay_enabled()` and `set_bypass_relay_enabled(bool)` read and
  write the bypass relay setting. The write is confirmed using the Modbus
  echo or a readback.

---

## 📚 Related
- [renac-ha-mqtt](https://github.com/voluzi/renac-ha-mqtt) – Home Assistant MQTT integration library for RENAC devices

---

## 📜 License
This project is open source and available under the [MIT License](LICENSE).
