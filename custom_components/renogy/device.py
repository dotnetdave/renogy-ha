"""BLE device representation for Renogy hardware.

This module contains a lightweight wrapper around :class:`~bleak.backends.device.BLEDevice`
that tracks state and parsed information for a single Renogy device.  Separating
the logic into its own file keeps the coordinator focused on BLE I/O while the
device class manages availability and parsing concerns.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from bleak.backends.device import BLEDevice

from .const import DEFAULT_DEVICE_TYPE, UNAVAILABLE_RETRY_INTERVAL, LOGGER
from .utils import clean_device_name

try:
    from renogy_ble import RenogyParser  # pragma: no cover

    PARSER_AVAILABLE = True
except ImportError:  # pragma: no cover - library optional in tests
    LOGGER.error("renogy-ble library not found! Please re-install the integration")
    RenogyParser = None
    PARSER_AVAILABLE = False


class RenogyBLEDevice:
    """Representation of a Renogy BLE device.

    The object stores connection details, last known data and convenience
    methods for tracking availability.  A reference to this object is kept by
    the :class:`RenogyActiveBluetoothCoordinator` so that entities can access
    parsed metrics even when the device is temporarily unavailable.
    """

    def __init__(
        self,
        ble_device: BLEDevice,
        advertisement_rssi: Optional[int] = None,
        device_type: str = DEFAULT_DEVICE_TYPE,
    ) -> None:
        self.ble_device = ble_device
        self.address = ble_device.address

        cleaned_name = clean_device_name(ble_device.name)
        self.name = cleaned_name or "Unknown Renogy Device"

        self.rssi = advertisement_rssi
        self.last_seen = datetime.now()
        self.data: Optional[Dict[str, Any]] = None
        self.failure_count = 0
        self.max_failures = 3
        self.available = True
        self.parsed_data: Dict[str, Any] = {}
        self.device_type = device_type
        self.last_unavailable_time: Optional[datetime] = None

    @property
    def is_available(self) -> bool:
        """Return ``True`` when the device is considered reachable."""
        return self.available and self.failure_count < self.max_failures

    @property
    def should_retry_connection(self) -> bool:
        """Check if enough time has passed to attempt a reconnect."""
        if self.is_available:
            return True

        if self.last_unavailable_time is None:
            self.last_unavailable_time = datetime.now()
            return False

        retry_time = self.last_unavailable_time + timedelta(
            minutes=UNAVAILABLE_RETRY_INTERVAL
        )
        if datetime.now() >= retry_time:
            LOGGER.debug(
                "Retry interval reached for unavailable device %s. Attempting reconnection...",
                self.name,
            )
            self.last_unavailable_time = datetime.now()
            return True

        return False

    def update_availability(self, success: bool, error: Optional[Exception] = None) -> None:
        """Update availability based on the success of communication attempts.

        The coordinator calls this method after each polling cycle.  If
        ``success`` is ``True`` the failure counter is reset and the device is
        marked available.  Otherwise the failure counter is incremented and once
        it reaches ``max_failures`` the device is considered unavailable until a
        successful poll occurs again.
        """
        if success:
            if self.failure_count > 0:
                LOGGER.info(
                    "Device %s communication restored after %s consecutive failures",
                    self.name,
                    self.failure_count,
                )
            self.failure_count = 0
            if not self.available:
                LOGGER.info("Device %s is now available", self.name)
                self.available = True
                self.last_unavailable_time = None
        else:
            self.failure_count += 1
            error_msg = f" Error message: {error}" if error else ""
            LOGGER.info(
                "Communication failure with Renogy device: %s. (Consecutive polling failure #%s. Device will be marked unavailable after %s failures.)%s",
                self.name,
                self.failure_count,
                self.max_failures,
                error_msg,
            )

            if self.failure_count >= self.max_failures and self.available:
                error_msg = f". Error message: {error}" if error else ""
                LOGGER.error(
                    "Renogy device %s marked unavailable after %s consecutive polling failures%s",
                    self.name,
                    self.max_failures,
                    error_msg,
                )
                self.available = False
                self.last_unavailable_time = datetime.now()

    def update_parsed_data(self, raw_data: bytes, register: int, cmd_name: str = "unknown") -> bool:
        """Parse ``raw_data`` from a read command and store the metrics.

        The low level BLE communication is handled by the coordinator.  Once a
        response is received it is passed here so that the ``renogy-ble``
        library can decode it into a Python dictionary.  Any errors are logged
        and ``False`` is returned to signal a failed parse.
        """
        if not raw_data:
            LOGGER.error(
                "Attempted to parse empty data from device %s for command %s.",
                self.name,
                cmd_name,
            )
            return False

        if not PARSER_AVAILABLE:
            LOGGER.error("RenogyParser library not available. Unable to parse data.")
            return False

        try:
            if len(raw_data) < 5:
                LOGGER.warning(
                    "Response too short for %s: %s bytes. Raw data: %s",
                    cmd_name,
                    len(raw_data),
                    raw_data.hex(),
                )
                return False

            byte_count = raw_data[2]
            expected_len = 3 + byte_count + 2
            if len(raw_data) < expected_len:
                LOGGER.warning(
                    "Got only %s / %s bytes for %s (register %s). Raw: %s",
                    len(raw_data),
                    expected_len,
                    cmd_name,
                    register,
                    raw_data.hex(),
                )
                return False
            function_code = raw_data[1] if len(raw_data) > 1 else 0
            if function_code & 0x80:
                error_code = raw_data[2] if len(raw_data) > 2 else 0
                LOGGER.error(
                    "Modbus error in %s response: function code %s, error code %s",
                    cmd_name,
                    function_code,
                    error_code,
                )
                return False

            parsed = RenogyParser.parse(raw_data, self.device_type, register)

            if not parsed:
                LOGGER.warning(
                    "No data parsed from %s response (register %s). Length: %s",
                    cmd_name,
                    register,
                    len(raw_data),
                )
                return False

            self.parsed_data.update(parsed)

            LOGGER.debug(
                "Successfully parsed %s data from device %s: %s",
                cmd_name,
                self.name,
                parsed,
            )
            return True

        except Exception as e:  # pragma: no cover - logging
            LOGGER.error(
                "Error parsing %s data from device %s: %s", cmd_name, self.name, e
            )
            LOGGER.debug(
                "Raw data for %s (register %s): %s, Length: %s",
                cmd_name,
                register,
                raw_data.hex() if raw_data else "None",
                len(raw_data) if raw_data else 0,
            )
            return False
