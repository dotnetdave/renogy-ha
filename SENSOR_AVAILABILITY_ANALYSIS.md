# Sensor Availability Issues - Analysis and Fixes

## Root Cause Analysis

After investigating why all sensors are showing as unavailable in the Home Assistant dashboard, I identified several key issues:

## Issues Found and Fixed

### 1. Missing `_device_type` Property (FIXED)
**Problem**: In `ble.py`, the coordinator initialization was setting `self.device_type = device_type` but the property getter/setter used `self._device_type`.

**Fix**: Changed to `self._device_type = device_type` in the constructor.

### 2. Missing `data` Property Initialization (FIXED)
**Problem**: The coordinator didn't initialize the `self.data` dictionary, which is required for sensor availability.

**Fix**: Added `self.data: Dict[str, Any] = {}` to coordinator initialization.

### 3. Insufficient Error Handling in `async_request_refresh` (FIXED)
**Problem**: When no service info was available (device not in range), the coordinator would log an error but not notify sensors, leaving them in an unknown state.

**Fix**: Added `self.async_update_listeners()` call when service info is missing, and improved logging to warn that this will cause unavailable sensors.

### 4. Enhanced Sensor Availability Debugging (FIXED)
**Problem**: The sensor availability logic was hard to debug.

**Fix**: Added detailed debug logging to the sensor's `available` property to show exactly why sensors are unavailable.

## Sensor Availability Logic

The sensor availability depends on three conditions:
1. `coordinator.last_update_success = True`
2. `device.is_available = True` (if device exists)
3. Either `device.parsed_data` or `coordinator.data` must have data

## Expected Flow

1. Integration starts → sensors created with empty data
2. Coordinator starts → begins BLE polling
3. First poll succeeds → populates `coordinator.data` and `device.parsed_data`
4. Coordinator calls `async_update_listeners()` → sensors check availability
5. Sensors become available

## Potential Remaining Issues

1. **BLE Device Not Found**: If the physical device is not in range or powered off, `bluetooth.async_last_service_info()` returns `None`, causing sensors to remain unavailable.

2. **BLE Connection Failures**: If the device is discoverable but BLE connection fails, polling will fail and sensors remain unavailable.

3. **Data Parsing Failures**: If the device responds but data parsing fails, `device.parsed_data` remains empty.

4. **Timing Issues**: There might be a brief window where sensors appear unavailable before first successful poll.

## Debugging Steps

1. **Enable Debug Logging**: Set Home Assistant logging level to DEBUG for `custom_components.renogy`

2. **Check Device Status**: Look for these log messages:
   - "No service info available for device X" → Device not discoverable
   - "Failed to establish connection" → BLE connection issues  
   - "Error parsing X data" → Data parsing issues
   - "Successfully parsed X data" → Successful data retrieval

3. **Monitor Data Flow**: Check if coordinator.data gets populated:
   - "Updated coordinator data: {...}" → Data successfully stored

## Testing

Created `debug_sensor_availability.py` script that confirms the availability logic works correctly in isolation. The issue is likely in the real-world BLE polling process.
