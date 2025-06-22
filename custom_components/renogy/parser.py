"""Parsing helpers for Renogy BLE integrations."""

from __future__ import annotations

from typing import Dict


def parse_shunt_packet(data: bytes) -> Dict[str, float | int | None]:
    """Parse a Renogy SmartShunt manufacturer specific packet."""
    if len(data) < 12:
        raise ValueError("packet too short")

    offset = 2  # skip manufacturer id
    if len(data) < offset + 10:
        raise ValueError("packet too short")

    bus_mv = int.from_bytes(data[offset : offset + 2], "big")
    offset += 2
    shunt_uv = int.from_bytes(data[offset : offset + 2], "big")
    offset += 2
    current_ma = int.from_bytes(data[offset : offset + 2], "big", signed=True)
    offset += 2
    consumed = int.from_bytes(data[offset : offset + 2], "big")
    offset += 2
    soc = data[offset]
    offset += 1
    temperature_raw = data[offset]
    offset += 1
    extra = data[offset] if len(data) > offset else None

    metrics = {
        "bus_voltage": bus_mv / 1000,
        "shunt_drop": shunt_uv / 1000,
        "current": current_ma / 1000,
        "consumed_ah": consumed / 100,
        "state_of_charge": max(0, min(soc, 100)),
        "temperature": temperature_raw - 40,
        "extra_flags": extra,
    }

    return metrics


def parse_shunt_ble_packet(data: bytes) -> Dict[str, float | int]:
    """Parse a SmartShunt BLE packet containing SOC (Function Code 0x03)."""
    if len(data) < 7:
        raise ValueError("packet too short")

    func_code = data[3]
    if func_code == 0x03:
        length = data[4]
        if length < 2 or len(data) < 5 + length:
            raise ValueError("invalid length")

        soc_raw = int.from_bytes(data[5:7], "big")
        return {
            "packetType": "0x0C03",
            "socRaw": soc_raw,
            "state_of_charge": min(max(soc_raw, 0), 100),  # Clamp 0–100
        }

    raise ValueError(f"Unsupported function code: 0x{func_code:02X}")
