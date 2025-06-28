"""Parsing helpers for Renogy BLE integrations."""

from __future__ import annotations

from typing import Any, Dict
import logging

LOGGER = logging.getLogger(__name__)


def _bytes_to_int(bs: bytes, offset: int, length: int, *, signed: bool = False, scale: float = 1.0) -> float | int | None:
    """Helper to convert a slice of ``bs`` into a scaled integer."""
    if len(bs) < offset + length:
        return None
    raw = int.from_bytes(bs[offset : offset + length], "big", signed=signed)
    value: float | int = raw * scale
    return round(value, 2) if isinstance(value, float) else value


def parse_shunt_packet(data: bytes) -> Dict[str, float | int | None]:
    """Parse a Renogy SmartShunt manufacturer specific packet."""
    LOGGER.debug("Parsing manufacturer packet: %s", data)
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
    LOGGER.debug("Parsed manufacturer packet data: %s", metrics)
    return metrics


def parse_shunt_ble_packet(data: bytes) -> Dict[str, float | int | str]:
    """Parse a SmartShunt BLE notification packet from characteristic FFF1."""
    LOGGER.debug("Parsing BLE packet: %s", data)

    # Filter out ASCII status strings like b"AT+NM=..." which aren't valid data
    if len(data) >= 2 and data[:2] == b"AT":
        LOGGER.debug("Ignoring ASCII status packet: %s", data)
        raise ValueError("status packet")

    if len(data) < 4:
        LOGGER.error("Packet too short to parse: %s", data)
        raise ValueError("packet too short")

    packet_type = data[2]
    LOGGER.debug("Detected packet type: 0x%02X", packet_type)

    if packet_type in (0x10, 0x44):
        payload = data[3:]
        LOGGER.debug("Extracted payload: %s", payload)

        if packet_type == 0x10:
            LOGGER.debug("Processing ASCII model ID string packet")
            model_id = payload.decode("ascii", errors="ignore").strip()
            LOGGER.debug("Parsed model ID: %s", model_id)
            return {"packetType": "0x10", "model_id": model_id}

        if packet_type == 0x44:
            LOGGER.debug("Processing numeric metrics packet")
            if len(payload) < 11:
                LOGGER.error("Payload too short for numeric metrics: %s", payload)
                raise ValueError("payload too short")

            bus_v = int.from_bytes(payload[0:2], "big") / 1000.0
            drop_mv = int.from_bytes(payload[2:4], "big") / 1000.0
            curr_a = int.from_bytes(payload[4:6], "big", signed=True) / 1000.0
            consumed_ah = int.from_bytes(payload[6:8], "big") / 100.0
            soc_raw = payload[8]
            soc = max(0, min(soc_raw, 100))
            temp_c = payload[9] - 40
            flags = payload[10]

            metrics = {
                "packetType": "0x44",
                "bus_voltage": bus_v,
                "shunt_drop": drop_mv,
                "current": curr_a,
                "consumed_ah": consumed_ah,
                "state_of_charge": soc,
                "temperature": temp_c,
                "extra_flags": flags,
            }
            metrics["power_watts"] = round(bus_v * curr_a, 2)
            LOGGER.debug("Parsed numeric metrics: %s", metrics)
            return metrics

        LOGGER.error("Unsupported packet type: 0x%02X", packet_type)
        raise ValueError(f"Unsupported packet type: 0x{packet_type:02X}")

    LOGGER.debug("Processing group-based message format")
    group_id = data[3]
    payload = data[4:]
    LOGGER.debug("Group ID: 0x%02X, Payload: %s", group_id, payload)

    metrics: Dict[str, float | int | str] = {"packetType": f"0x{group_id:02X}"}

    if group_id == 0x03:
        raw = int.from_bytes(payload[3:5], "little")
        metrics["state_of_charge"] = round(raw * 0.1, 1)
        LOGGER.debug("Parsed state_of_charge: %s", metrics["state_of_charge"])
        return metrics

    if group_id == 0x05:
        raw = int.from_bytes(payload[3:7], "little")
        metrics["battery_voltage"] = round(raw * 0.001, 3)
        LOGGER.debug("Parsed battery_voltage: %s", metrics["battery_voltage"])
        return metrics

    if group_id == 0x04:
        raw = int.from_bytes(payload[3:6], "little", signed=True)
        amps = round(raw * 0.001, 3)
        metrics["discharge_amps"] = amps
        LOGGER.debug("Parsed discharge_amps: %s", amps)
        if "battery_voltage" in metrics:
            metrics["power_watts"] = round(metrics["battery_voltage"] * amps, 2)
            LOGGER.debug("Calculated power_watts: %s", metrics["power_watts"])
        return metrics

    if group_id == 0x02:
        mins = _bytes_to_int(payload, 3, 4)
        if mins is not None:
            metrics["remaining_time_h"] = round(mins / 60, 2)
            LOGGER.debug("Parsed remaining_time_h: %s", metrics["remaining_time_h"])
        return metrics

    if group_id == 0x0B:
        metrics["consumed_Ah"] = _bytes_to_int(payload, 3, 4, scale=0.1)
        LOGGER.debug("Parsed consumed_Ah: %s", metrics["consumed_Ah"])
        return metrics

    if group_id == 0x06:
        mins = _bytes_to_int(payload, 3, 2)
        if mins is not None:
            metrics["discharge_duration_h"] = round(mins / 60, 2)
            LOGGER.debug("Parsed discharge_duration_h: %s", metrics["discharge_duration_h"])
        return metrics

    if group_id == 0x0D:
        metrics["temperature_C"] = _bytes_to_int(payload, 3, 2, signed=True, scale=0.1)
        LOGGER.debug("Parsed temperature_C: %s", metrics["temperature_C"])
        return metrics

    if group_id == 0x07:
        metrics["starter_volts"] = _bytes_to_int(payload, 3, 4, scale=0.001)
        LOGGER.debug("Parsed starter_volts: %s", metrics["starter_volts"])
        return metrics

    LOGGER.error("Unsupported group ID: 0x%02X", group_id)
    raise ValueError(f"Unsupported group id: 0x{group_id:02X}")


def parse_shunt_ble_messages(messages: list[bytes]) -> Dict[str, float | int | str]:
    """Parse multiple SmartShunt BLE packets and merge the metrics."""
    LOGGER.debug("Starting to parse BLE messages: %s", messages)
    result: Dict[str, float | int | str] = {}
    for index, msg in enumerate(messages):
        LOGGER.debug("Processing message %d: %s", index, msg)
        try:
            LOGGER.debug("Attempting to parse message %d: %s", index, msg)
            metrics = parse_shunt_ble_packet(msg)
            LOGGER.debug("Successfully parsed message %d: %s", index, metrics)
        except ValueError as e:
            LOGGER.warning("Failed to parse message %d: %s, Error: %s", index, msg, e)
            continue
        result.update(metrics)
        LOGGER.debug("Updated result after message %d: %s", index, result)

    LOGGER.debug("Final merged metrics after parsing all messages: %s", result)
    bus_v = result.get("battery_voltage") or result.get("bus_voltage")
    amps = result.get("discharge_amps") or result.get("current")
    if bus_v is not None and amps is not None:
        result["power_watts"] = round(float(bus_v) * float(amps), 2)
        LOGGER.debug("Calculated power_watts: %s", result["power_watts"])
    else:
        LOGGER.debug("Could not calculate power_watts due to missing bus_v or amps")

    LOGGER.debug("Returning final result: %s", result)
    return result
