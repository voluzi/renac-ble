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

    await inverter.disconnect()
    await wallbox.disconnect()

asyncio.run(main())
```

---

## 📚 Related
- [renac-ha-mqtt](https://github.com/voluzi/renac-ha-mqtt) – Home Assistant MQTT integration library for RENAC devices

---

## 📜 License
This project is open source and available under the [MIT License](LICENSE).
