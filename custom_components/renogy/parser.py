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


def parse_shunt_ble_packet(data: bytes) -> Dict[str, float | int | str]:
    """Parse a SmartShunt BLE notification packet from characteristic FFF1."""

    if len(data) < 4:
        raise ValueError("packet too short")

    packet_type = data[2]
    payload = data[3:]

    if packet_type == 0x10:
        # ASCII model ID string
        model_id = payload.decode("ascii", errors="ignore").strip()
        return {"packetType": "0x10", "model_id": model_id}

    if packet_type == 0x44:
        if len(payload) < 11:
            raise ValueError("payload too short")

        bus_v = int.from_bytes(payload[0:2], "big") / 1000.0
        drop_mv = int.from_bytes(payload[2:4], "big") / 1000.0
        curr_a = int.from_bytes(payload[4:6], "big", signed=True) / 1000.0
        consumed_ah = int.from_bytes(payload[6:8], "big") / 100.0
        soc_raw = payload[8]
        soc = max(0, min(soc_raw, 100))
        temp_c = payload[9] - 40
        flags = payload[10]

        return {
            "packetType": "0x44",
            "bus_voltage": bus_v,
            "shunt_drop": drop_mv,
            "current": curr_a,
            "consumed_ah": consumed_ah,
            "state_of_charge": soc,
            "temperature": temp_c,
            "extra_flags": flags,
        }

    raise ValueError(f"Unsupported packet type: 0x{packet_type:02X}")
