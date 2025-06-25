#!/usr/bin/env python3
"""Test script to verify coordinator and sensor interaction."""

KEY_BATTERY_VOLTAGE = "battery_voltage"
KEY_BATTERY_PERCENTAGE = "battery_percentage"

class MockCoordinator:
    """Mock coordinator that simulates the real coordinator behavior."""
    
    def __init__(self):
        self.last_update_success = True
        self.data = {}
        self.device = None
        self._listeners = []
    
    def async_update_listeners(self):
        """Notify all listeners of updates."""
        print(f"Coordinator notifying {len(self._listeners)} listeners")
        for listener in self._listeners:
            listener()
    
    def simulate_successful_poll(self):
        """Simulate a successful device poll."""
        print("=== Simulating successful device poll ===")
        
        # Create mock device with data
        device = MockDevice()
        device.parsed_data = {
            KEY_BATTERY_VOLTAGE: 12.6,
            KEY_BATTERY_PERCENTAGE: 85
        }
        device.is_available = True
        
        # Update coordinator state
        self.device = device
        self.data = dict(device.parsed_data)
        self.last_update_success = True
        
        print(f"Coordinator data: {self.data}")
        print(f"Device data: {device.parsed_data}")
        
        # Notify listeners
        self.async_update_listeners()


class MockDevice:
    """Mock device."""
    
    def __init__(self):
        self.name = "Test Renogy Device"
        self.address = "AA:BB:CC:DD:EE:FF"
        self.is_available = True
        self.parsed_data = {}


class MockSensor:
    """Mock sensor that mimics RenogyBLESensor behavior."""
    
    def __init__(self, coordinator, name):
        self.coordinator = coordinator
        self.name = name
        self._device = None
        
        # Register with coordinator
        self.coordinator._listeners.append(self._handle_coordinator_update)
    
    @property
    def device(self):
        """Get device from coordinator if not set."""
        if self._device:
            return self._device
        if hasattr(self.coordinator, "device") and self.coordinator.device:
            self._device = self.coordinator.device
        return self._device
    
    @property
    def available(self):
        """Check if sensor is available."""
        # Check coordinator success
        if not self.coordinator.last_update_success:
            return False
        
        # Check device availability
        device = self.device
        if device and not device.is_available:
            return False
        
        # Check data availability
        if device and device.parsed_data:
            return True
        elif self.coordinator.data:
            return True
        
        return False
    
    def _handle_coordinator_update(self):
        """Handle coordinator updates."""
        print(f"Sensor {self.name} received coordinator update")
        print(f"  Available: {self.available}")
        if self.available:
            value = self.get_value()
            print(f"  Value: {value}")
    
    def get_value(self):
        """Get sensor value."""
        device = self.device
        if device and device.parsed_data:
            return device.parsed_data.get(KEY_BATTERY_VOLTAGE)
        return self.coordinator.data.get(KEY_BATTERY_VOLTAGE)


def test_coordinator_sensor_flow():
    """Test the complete flow from coordinator to sensors."""
    
    print("=== Testing Coordinator-Sensor Flow ===")
    
    # Create coordinator and sensors
    coordinator = MockCoordinator()
    voltage_sensor = MockSensor(coordinator, "Battery Voltage")
    percentage_sensor = MockSensor(coordinator, "Battery Percentage")
    
    print(f"\nInitial state:")
    print(f"Voltage sensor available: {voltage_sensor.available}")
    print(f"Percentage sensor available: {percentage_sensor.available}")
    
    # Simulate coordinator starting and polling device
    print(f"\nSimulating device poll...")
    coordinator.simulate_successful_poll()
    
    print(f"\nFinal state:")
    print(f"Voltage sensor available: {voltage_sensor.available}")
    print(f"Percentage sensor available: {percentage_sensor.available}")


if __name__ == "__main__":
    test_coordinator_sensor_flow()
