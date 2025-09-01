import asyncio
from bleak import BleakScanner, BleakClient

TARGET_NAME = "HF-LPT270"

async def explore_device(device):
    async with BleakClient(device) as client:  # pass full device object
        print(f"\n🔌 Connected to {device.name} [{device.address}]")
        print("📡 Discovering services and characteristics...\n")

        for service in client.services:
            print(f"🔧 Service: {service.uuid}")
            for char in service.characteristics:
                props = ', '.join(char.properties)
                print(f"  └─ 📍 Characteristic: {char.uuid} | Properties: {props}")

        print(f"✅ Finished setup for {device.name} [{device.address}] — listening for notifications...\n")

async def main():
    print("🔍 Scanning for BLE devices...")
    devices = await BleakScanner.discover(timeout=15.0)

    matching_devices = [d for d in devices if d.name == TARGET_NAME]
    if not matching_devices:
        print(f"\n❌ No devices found with name '{TARGET_NAME}'")
        return

    print(f"\n✅ Found {len(matching_devices)} matching devices:")
    for d in matching_devices:
        print(f" - {d.name} [{d.address}]")

    # Explore all in parallel using full device object (NOT just address)
    await asyncio.gather(*(explore_device(d) for d in matching_devices))

asyncio.run(main())