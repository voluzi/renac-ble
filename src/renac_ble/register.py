"""Typed definitions for RENAC Modbus registers."""

from typing import TypedDict, Literal, List


class Register(TypedDict):
    address: int
    count: int
    fmt: Literal["uint16", "int16", "uint32", "int32", "ascii", "custom"]
    scale: float
    unit: str


class RegisterField(TypedDict):
    name: str
    offset: int  # byte offset within the payload
    length: int  # number of bytes (e.g., 2 for uint16, 4 for uint32)
    fmt: Literal["ascii", "uint16", "int16", "uint32", "int32", "custom"]
    scale: float
    unit: str


class RegisterBlock(TypedDict):
    address: int
    count: int
    fields: List[RegisterField]

