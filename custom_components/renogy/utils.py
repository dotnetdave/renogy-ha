"""Utility helpers for the Renogy BLE integration.

This module contains small helper functions that are shared across the
integration.  Keeping them here avoids circular imports and makes it easy to
unit test the helpers in isolation.
"""

from __future__ import annotations

import re
from typing import Tuple


class ModbusUtils:
    """Helper methods for building and validating Modbus frames.

    The Renogy devices communicate over BLE using Modbus frames wrapped inside
    the BLE packets.  These helpers generate request frames and validate the
    responses using the standard CRC16 algorithm used by Modbus devices.
    """

    @staticmethod
    def crc16(data: bytes) -> Tuple[int, int]:
        """Calculate the Modbus CRC16 checksum for ``data``.

        The algorithm implemented here matches the one required by the Renogy
        charge controllers.  It iterates over every byte and builds the 16‑bit
        CRC which is returned as the low and high byte pair.
        """
        crc = 0xFFFF
        for pos in data:
            crc ^= pos
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc & 0xFF, (crc >> 8) & 0xFF

    @staticmethod
    def create_read_request(
        device_id: int, function_code: int, register: int, word_count: int
    ) -> bytearray:
        """Build a Modbus read request frame.

        ``device_id``       -- slave address of the target device
        ``function_code``   -- Modbus function to execute (usually ``0x03``)
        ``register``        -- starting register address
        ``word_count``      -- number of registers to read
        """
        # Basic Modbus request structure before CRC
        frame = bytearray(
            [
                device_id,
                function_code,
                (register >> 8) & 0xFF,
                register & 0xFF,
                (word_count >> 8) & 0xFF,
                word_count & 0xFF,
            ]
        )
        crc_low, crc_high = ModbusUtils.crc16(frame)
        frame.extend([crc_low, crc_high])
        return frame


def clean_device_name(name: str) -> str:
    """Return a sanitized device name.

    The BLE name broadcast by the devices often contains trailing spaces or
    duplicated whitespace.  This helper normalises the name so that the rest of
    the integration can rely on a consistent value.
    """
    if not name:
        return ""
    cleaned_name = name.strip()
    return re.sub(r"\s+", " ", cleaned_name).strip()
