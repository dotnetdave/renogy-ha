"""Constants for the Renogy BLE integration."""

import logging
from enum import Enum

DOMAIN = "renogy"

LOGGER = logging.getLogger(__name__)

# BLE scanning constants
DEFAULT_SCAN_INTERVAL = 60  # seconds
MIN_SCAN_INTERVAL = 10  # seconds
MAX_SCAN_INTERVAL = 600  # seconds

# Renogy device name prefixes used for discovery
RENOGY_BT_PREFIX = "BT-TH-"
RENOGY_RTM_PREFIX = "RTM"
RENOGY_NAME_PREFIXES = (RENOGY_BT_PREFIX, RENOGY_RTM_PREFIX)
RENOGY_SHUNT_MANUF_ID = 0x4C00

# Configuration parameters
CONF_SCAN_INTERVAL = "scan_interval"
CONF_DEVICE_TYPE = "device_type"  # New constant for device type

# Device info
ATTR_MANUFACTURER = "Renogy"


# Define device types as Enum
class DeviceType(Enum):
    CONTROLLER = "controller"
    BATTERY = "battery"
    INVERTER = "inverter"
    SHUNT = "shunt"


# List of supported device types
DEVICE_TYPES = [e.value for e in DeviceType]
DEFAULT_DEVICE_TYPE = DeviceType.CONTROLLER.value

# List of fully supported device types
SUPPORTED_DEVICE_TYPES = [
    DeviceType.CONTROLLER.value,
    DeviceType.SHUNT.value,
]

# BLE Characteristics and Service UUIDs
RENOGY_READ_CHAR_UUID = (
    "0000fff1-0000-1000-8000-00805f9b34fb"  # Characteristic for reading data
)
RENOGY_WRITE_CHAR_UUID = (
    "0000ffd1-0000-1000-8000-00805f9b34fb"  # Characteristic for writing commands
)

# --- SmartShunt BLE Service and Characteristic UUIDs ---
RENOGY_SHUNT_SERVICE_UUID = "0000c011-0000-1000-8000-00805f9b34fb"
RENOGY_SHUNT_WRITE_CHAR_UUID = "0000c111-0000-1000-8000-00805f9b34fb"
RENOGY_SHUNT_NOTIFY_CHAR_UUID = "0000c411-0000-1000-8000-00805f9b34fb"
RENOGY_SHUNT_CCCD_UUID = "00002902-0000-1000-8000-00805f9b34fb"

# Time in minutes to wait before attempting to reconnect to unavailable devices
UNAVAILABLE_RETRY_INTERVAL = 10

# Maximum time to wait for a notification response (seconds)
MAX_NOTIFICATION_WAIT_TIME = 2.0

# Default device ID for Renogy devices
DEFAULT_DEVICE_ID = 0xFF

# SmartShunt sensor keys
KEY_SHUNT_BUS_VOLTAGE = "bus_voltage"
KEY_SHUNT_SHUNT_DROP = "shunt_drop"
KEY_SHUNT_CURRENT = "current"
KEY_SHUNT_CONSUMED_AH = "consumed_ah"
KEY_SHUNT_STATE_OF_CHARGE = "state_of_charge"
KEY_SHUNT_TEMPERATURE = "temperature"
KEY_SHUNT_EXTRA_FLAGS = "extra_flags"

# Modbus commands for requesting data
COMMANDS = {
    DeviceType.CONTROLLER.value: {
        "device_info": (3, 12, 8),
        "device_id": (3, 26, 1),
        "battery": (3, 57348, 1),
        "pv": (3, 256, 34),
    },
}
