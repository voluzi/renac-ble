# renac-ble

A Python library for communicating with RENAC inverters and wallboxes via Bluetooth Low Energy (BLE).

## Installation

You can install the package directly from the source:

```bash
pip install -e .
```

## Usage

```python
import asyncio
from renac_ble import RenacInverterBLE

async def main():
    inverter = RenacInverterBLE("AA:BB:CC:DD:EE:FF")
    await inverter.connect()
    # interact with registers here
    await inverter.disconnect()

asyncio.run(main())
```

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
