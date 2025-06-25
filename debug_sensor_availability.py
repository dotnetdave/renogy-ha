#!/usr/bin/env python3
"""Debug script to test sensor availability logic."""

# Mock constants
KEY_BATTERY_VOLTAGE = "battery_voltage"
KEY_BATTERY_PERCENTAGE = "battery_percentage"


class MockCoordinator:
    """Mock coordinator for testing."""
    
    def __init__(self):
        self.last_update_success = True
        self.data = {}
        self.device = None


class MockDevice:
    """Mock device for testing."""
    
    def __init__(self):
        self.name = "Test Device"
        self.address = "AA:BB:CC:DD:EE:FF"
        self.is_available = True
        self.parsed_data = {}


class MockSensorDescription:
    """Mock sensor description."""
    
    def __init__(self, key):
        self.key = key
        self.name = f"Test {key}"


class MockSensor:
    """Mock sensor to test availability logic."""
    
    def __init__(self, coordinator, device=None):
        self.coordinator = coordinator
        self._device = device
        self.entity_description = MockSensorDescription(KEY_BATTERY_VOLTAGE)
        self.name = f"Mock Sensor {self.entity_description.key}"
    
    @property
    def device(self):
        """Get the current device - either stored or from coordinator."""
        if self._device:
            return self._device
        # Try to get device from coordinator
        if hasattr(self.coordinator, "device") and self.coordinator.device:
            self._device = self.coordinator.device
        return self._device
    
    @property
    def available(self) -> bool:
        """Return if the sensor is available."""
        # Basic coordinator availability check
        if not self.coordinator.last_update_success:
            print(f"Sensor {self.name} unavailable: coordinator last_update_success is False")
            return False

        # Check device availability if we have a device
        device = self.device
        if device and not device.is_available:
            print(f"Sensor {self.name} unavailable: device {device.name} is not available")
            return False

        # For the actual data, check either the device's parsed_data or coordinator's data
        data_available = False
        if device and device.parsed_data:
            data_available = True
            print(f"Sensor {self.name} available: device has parsed_data with {len(device.parsed_data)} keys")
        elif self.coordinator.data:
            data_available = True
            print(f"Sensor {self.name} available: coordinator has data with {len(self.coordinator.data)} keys")
        else:
            print(f"Sensor {self.name} unavailable: no data in device.parsed_data or coordinator.data")

        return data_available


def test_scenarios():
    """Test different availability scenarios."""
    
    print("=== Testing Sensor Availability Logic ===")
    
    # Scenario 1: Fresh coordinator, no device, no data
    print("\n1. Fresh coordinator, no device, no data:")
    coordinator = MockCoordinator()
    sensor = MockSensor(coordinator)
    print(f"Available: {sensor.available}")
    
    # Scenario 2: Coordinator with data, no device
    print("\n2. Coordinator with data, no device:")
    coordinator.data = {KEY_BATTERY_VOLTAGE: 12.5}
    print(f"Available: {sensor.available}")
    
    # Scenario 3: Coordinator with device but no data
    print("\n3. Coordinator with device but no data:")
    coordinator.data = {}
    coordinator.device = MockDevice()
    print(f"Available: {sensor.available}")
    
    # Scenario 4: Coordinator with device and device has data
    print("\n4. Coordinator with device and device has data:")
    coordinator.device.parsed_data = {KEY_BATTERY_VOLTAGE: 12.5, KEY_BATTERY_PERCENTAGE: 85}
    print(f"Available: {sensor.available}")
    
    # Scenario 5: Device unavailable
    print("\n5. Device unavailable:")
    coordinator.device.is_available = False
    print(f"Available: {sensor.available}")
    
    # Scenario 6: Coordinator update failed
    print("\n6. Coordinator update failed:")
    coordinator.device.is_available = True
    coordinator.last_update_success = False
    print(f"Available: {sensor.available}")


if __name__ == "__main__":
    test_scenarios()
