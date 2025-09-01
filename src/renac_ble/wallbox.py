"""Helpers for interacting with RENAC wallbox chargers."""

import logging
import struct
from datetime import datetime
from typing import Callable, Optional

from renac_ble.ble import RenacBLE

logger = logging.getLogger(__name__)


class RenacWallboxBLE(RenacBLE):
    """BLE client for RENAC wallbox chargers."""

    def __init__(
        self, address: str, on_notification: Optional[Callable[[dict], None]] = None
    ) -> None:
        self._parsed_callback = on_notification
        super().__init__(address, notification_callback=self._handle_raw_notification)

    def _handle_raw_notification(self, data: bytes) -> None:
        """Parse raw BLE payloads and dispatch structured data."""

        if is_wallbox_notification(data):
            parsed = parse_wallbox_notification(data)
            if self._parsed_callback:
                self._parsed_callback(parsed)


def is_wallbox_notification(data: bytes) -> bool:
    """Return ``True`` if ``data`` looks like a wallbox notification."""

    if data is None or not data.startswith(b"#SOCKA#") or len(data) < 10:
        return False
    payload = data[7:]
    if len(payload) < 3:
        return False
    return payload[1] == 0x03 and payload[2] == 0x8E


def get_renac_charger_state(code: int) -> str:
    """Map integer status codes to human readable strings."""

    return {
        0: "idle",
        1: "scheduled",
        2: "paused",
        3: "charging",
        4: "completed",
        5: "error"
    }.get(code, "")


def parse_wallbox_notification(data: bytes) -> Optional[dict]:
    """Parse a wallbox notification payload into a dictionary."""

    if not data.startswith(b"#SOCKA#"):
        raise ValueError("Invalid message: missing #SOCKA# header")
    payload = data[7:]  # remove '#SOCKA#'
    result: dict[str, object] = {}
    try:
        result["model"] = payload[3:35].decode("ascii", errors="ignore").strip("\x00").strip()
        result["sn"] = payload[35:67].decode("ascii", errors="ignore").strip("\x00").strip()
        result["manufacturer"] = payload[67:99].decode("ascii", errors="ignore").strip("\x00").strip()

        result["version"] = f'V{struct.unpack(">H", payload[99:101])[0] / 100:.2f}'
        result["state"] = get_renac_charger_state(struct.unpack(">H", payload[101:103])[0])
        result["phase_a_voltage"] = struct.unpack(">H", payload[103:105])[0] / 10
        result["phase_a_current"] = struct.unpack(">H", payload[105:107])[0] / 10
        result["phase_b_voltage"] = struct.unpack(">H", payload[107:109])[0] / 10
        result["phase_b_current"] = struct.unpack(">H", payload[109:111])[0] / 10
        result["phase_c_voltage"] = struct.unpack(">H", payload[111:113])[0] / 10
        result["phase_c_current"] = struct.unpack(">H", payload[113:115])[0] / 10
        result["power"] = struct.unpack(">H", payload[115:117])[0]
        result["temperature"] = struct.unpack(">H", payload[117:119])[0] / 10
        result["current_charging_amount"] = struct.unpack(">H", payload[119:121])[0] / 10
        result["current_charging_time"] = struct.unpack(">H", payload[121:123])[0] / 10
        result["total_charge"] = struct.unpack(">I", payload[127:131])[0] / 10
        result["update_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    except Exception as e:  # pragma: no cover - best effort parsing
        logger.exception("Error parsing wallbox notification")
        result["error"] = f"Error parsing: {e}"

    return result
