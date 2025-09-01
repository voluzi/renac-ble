from importlib.metadata import PackageNotFoundError, version as _version

try:
    __version__ = _version("renac-ble")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

# Public API (kept for backward compatibility)
from .ble import RenacBLE
from .wallbox import RenacWallboxBLE
from .inverter import RenacInverterBLE

_regs_all: list[str]
try:
    from .inverter_registers import *  # noqa: F401,F403
    try:
        from .inverter_registers import __all__ as _regs_all  # type: ignore[attr-defined]
    except Exception:
        _regs_all = []
except Exception:
    _regs_all = []

__all__ = [
    "__version__",
    "RenacBLE",
    "RenacWallboxBLE",
    "RenacInverterBLE",
    *_regs_all,
]