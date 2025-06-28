"""BLE communication module for Renogy devices.

``RenogyActiveBluetoothCoordinator`` handles all BLE interaction and is shared
between one or more sensor entities.  It is responsible for establishing the
connection, issuing Modbus read requests and passing the resulting data to the
``RenogyBLEDevice`` instance for parsing.  The coordinator is designed to be
mostly self contained so that higher level modules only need to subscribe to its
updates.
"""

import asyncio
import logging
import traceback
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

from homeassistant.components.bluetooth.active_update_coordinator import (
    ActiveBluetoothDataUpdateCoordinator,
)
from homeassistant.core import CoreState, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.components import bluetooth

from bleak.exc import BleakError
from bleak_retry_connector import establish_connection, BleakClientWithServiceCache

from .const import (
    COMMANDS,
    DEFAULT_DEVICE_ID,
    DEFAULT_DEVICE_TYPE,
    DEFAULT_SCAN_INTERVAL,
    LOGGER,
    MAX_NOTIFICATION_WAIT_TIME,
    RENOGY_READ_CHAR_UUID,
    RENOGY_WRITE_CHAR_UUID,
    RENOGY_SHUNT_SERVICE_UUID,
    UNAVAILABLE_RETRY_INTERVAL,
    RENOGY_SHUNT_MANUF_ID,
    DeviceType,
    RENOGY_SHUNT_WRITE_CHAR_UUID,
    RENOGY_SHUNT_NOTIFY_CHAR_UUID,
    RENOGY_SHUNT_CCCD_UUID, 
)
from .parser import parse_shunt_ble_packet, parse_shunt_packet
from .device import RenogyBLEDevice
from .utils import ModbusUtils, clean_device_name

try:
    from renogy_ble import RenogyParser

    PARSER_AVAILABLE = True
except ImportError:
    LOGGER.error("renogy-ble library not found! Please re-install the integration")
    RenogyParser = None
    PARSER_AVAILABLE = False

try:
    from homeassistant.components.bluetooth import BluetoothScanningMode
except (ImportError, AttributeError):
    BluetoothScanningMode = None
    LOGGER.warning(
        "BluetoothScanningMode not available in this Home Assistant version; using default scan mode."
    )

# Fix undefined symbols and ensure proper error handling

# Define missing symbols
BleakConnectionError = Exception  # Placeholder for undefined BleakConnectionError
BleakDBusError = Exception  # Placeholder for undefined BleakDBusError


class RenogyActiveBluetoothCoordinator(ActiveBluetoothDataUpdateCoordinator):
    """Class to manage fetching Renogy BLE data via active connections.

    The coordinator polls a single BLE device at a configurable interval.  It
    exposes the parsed data to Home Assistant listeners and keeps track of the
    device availability.  A small state machine prevents overlapping connection
    attempts while still supporting manual refresh requests.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        logger: logging.Logger,
        *,
        address: str,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
        device_type: str = DEFAULT_DEVICE_TYPE,
        device_data_callback: Optional[Callable[[RenogyBLEDevice], None]] = None,
    ):
        """Initialize the coordinator with Home Assistant context.

        Parameters are mostly passed straight through from the config entry.
        ``device_data_callback`` allows the caller to receive the
        :class:`RenogyBLEDevice` instance whenever new data is parsed.
        """
        super().__init__(
            hass=hass,
            logger=logger,
            address=address,
            needs_poll_method=self._needs_poll,
            poll_method=self._async_poll,
            mode=BluetoothScanningMode.ACTIVE if BluetoothScanningMode else None,
            connectable=True,
        )
        self.device: Optional[RenogyBLEDevice] = None
        self.scan_interval = scan_interval
        self._device_type = device_type
        self.last_poll_time: Optional[datetime] = None
        self.device_data_callback = device_data_callback
        self.logger.debug(
            "Initialized coordinator for %s as %s with %ss interval",
            address,
            device_type,
            scan_interval,
        )

        # Add required properties for Home Assistant CoordinatorEntity compatibility
        self.last_update_success = True
        self.data: Dict[str, Any] = {}
        self._listeners = []
        self.update_interval = timedelta(seconds=scan_interval)
        self._unsub_refresh = None
        self._request_refresh_task = None

        # Add connection lock to prevent multiple concurrent connections
        self._connection_lock = asyncio.Lock()
        self._connection_in_progress = False

    @property
    def device_type(self) -> str:
        """Get the device type from configuration."""
        return self._device_type

    @device_type.setter
    def device_type(self, value: str) -> None:
        """Set the device type."""
        self._device_type = value

    async def async_request_refresh(self) -> None:
        """Request a refresh."""
        self.logger.debug("Manual refresh requested for device %s", self.address)

        # If a connection is already in progress, don't start another one
        if self._connection_in_progress:
            self.logger.debug(
                "Connection already in progress, skipping refresh request"
            )
            return

        # Get the last available service info for this device
        service_info = bluetooth.async_last_service_info(self.hass, self.address)
        if not service_info:
            self.logger.error(
                "No service info available for device %s. Ensure device is within range and powered on.",
                self.address,
            )
            self.last_update_success = False
            return

        try:
            await self._async_poll(service_info)
            self.last_update_success = True
            # Notify listeners of the update
            for update_callback in self._listeners:
                update_callback()
        except Exception as err:
            self.last_update_success = False
            error_traceback = traceback.format_exc()
            self.logger.debug(
                "Error refreshing device %s: %s\n%s",
                self.address,
                str(err),
                error_traceback,
            )
            if self.device:
                self.device.update_availability(False, err)

    def async_add_listener(
        self, update_callback: Callable[[], None], context: Any = None
    ) -> Callable[[], None]:
        """Listen for data updates."""
        if update_callback not in self._listeners:
            self._listeners.append(update_callback)

        def remove_listener() -> None:
            """Remove update callback."""
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return remove_listener

    def async_update_listeners(self) -> None:
        """Update all registered listeners."""
        # Don't update listeners if Home Assistant is not running (shutdown)
        if self.hass.state not in (CoreState.starting, CoreState.running):
            self.logger.debug("Skipping listener updates - Home Assistant is shutting down")
            return

        for update_callback in self._listeners:
            try:
                update_callback()
            except Exception as e:
                self.logger.debug("Error in listener callback during shutdown: %s", e)

    def _schedule_refresh(self) -> None:
        """Schedule a refresh with the update interval."""
        if self._unsub_refresh:
            self._unsub_refresh()
            self._unsub_refresh = None

        # Schedule the next refresh based on our scan interval
        self._unsub_refresh = async_track_time_interval(
            self.hass, self._handle_refresh_interval, self.update_interval
        )
        self.logger.debug("Scheduled next refresh in %s seconds", self.scan_interval)

    async def _handle_refresh_interval(self, _now=None):
        """Handle a refresh interval occurring."""
        # Prevent refresh if Home Assistant is shutting down
        try:
            if self.hass.state not in (CoreState.starting, CoreState.running):
                self.logger.debug(
                    "Skipping refresh interval - Home Assistant is shutting down"
                )
                return
            self.logger.debug("Regular interval refresh for %s", self.address)
            await self.async_request_refresh()
        except Exception as e:
            # Expected during shutdown; prevents event loop errors
            self.logger.debug("Error during refresh interval (likely shutdown): %s", e)

    def async_start(self) -> Callable[[], None]:
        """Start polling."""
        self.logger.debug("Starting polling for device %s", self.address)

        def _unsub() -> None:
            """Unsubscribe from updates."""
            if self._unsub_refresh:
                self._unsub_refresh()
                self._unsub_refresh = None

        _unsub()  # Cancel any previous subscriptions

        # We use the active update coordinator's start method
        # which already handles the bluetooth subscriptions
        result = super().async_start()

        # Schedule regular refreshs at our configured interval
        self._schedule_refresh()

        # Perform an initial refresh and track the task
        self._request_refresh_task = self.hass.async_create_task(self.async_request_refresh())

        return result

    def _async_cancel_bluetooth_subscription(self) -> None:
        """Cancel the bluetooth subscription."""
        if hasattr(self, "_unsubscribe_bluetooth") and self._unsubscribe_bluetooth:
            self._unsubscribe_bluetooth()
            self._unsubscribe_bluetooth = None

    def async_stop(self) -> None:
        """Stop polling and clean up all resources."""
        self.logger.debug("Stopping coordinator for device %s", self.address)

        # Prevent new operations
        self._connection_in_progress = False

        # Cancel scheduled refresh to prevent further tasks
        if self._unsub_refresh:
            try:
                self._unsub_refresh()
            except Exception as e:
                self.logger.debug("Error canceling refresh schedule: %s", e)
            finally:
                self._unsub_refresh = None

        # Cancel in-flight refresh task if pending
        if getattr(self, '_request_refresh_task', None) and \
           not self._request_refresh_task.done():
            try:
                self._request_refresh_task.cancel()
            except Exception as e:
                self.logger.debug("Error canceling in-flight refresh task: %s", e)
            finally:
                self._request_refresh_task = None

        # Cancel bluetooth subscriptions
        try:
            self._async_cancel_bluetooth_subscription()
        except Exception as e:
            self.logger.debug("Error canceling Bluetooth subscription: %s", e)

        # Clean up listeners
        self._listeners = []

        # Call parent cleanup safely
        try:
            super().async_stop()
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                self.logger.debug("Event loop already closed during shutdown - normal scenario")
            else:
                self.logger.debug("RuntimeError in parent async_stop: %s", e)
        except Exception as e:
            self.logger.debug("Error during parent async_stop: %s", e)

    @callback
    def _needs_poll(
        self,
        service_info: BluetoothServiceInfoBleak,
        last_poll: float | None,
    ) -> bool:
        """Determine if device needs polling based on time since last poll."""
        # Only poll if hass is running and device is connectable
        if self.hass.state != CoreState.running:
            return False

        # Check if we have a connectable device
        connectable_device = bluetooth.async_ble_device_from_address(
            self.hass, service_info.device.address, connectable=True
        )
        if not connectable_device:
            self.logger.warning(
                "No connectable device found for %s", service_info.address
            )
            return False

        # If a connection is already in progress, don't start another one
        if self._connection_in_progress:
            self.logger.debug("Connection already in progress, skipping poll")
            return False

        # If we've never polled or it's been longer than the scan interval, poll
        if last_poll is None:
            self.logger.debug("First poll for device %s", service_info.address)
            return True

        # Check if enough time has elapsed since the last poll
        time_since_poll = datetime.now().timestamp() - last_poll
        should_poll = time_since_poll >= self.scan_interval

        if should_poll:
            self.logger.debug(
                "Time to poll device %s after %.1fs",
                service_info.address,
                time_since_poll,
            )

        return should_poll

    async def _read_device_data(self, service_info: BluetoothServiceInfoBleak) -> bool:
        """Read data from a Renogy BLE device using an active connection."""
        async with self._connection_lock:
            self._connection_in_progress = True
            try:
                # Prepare or update RenogyBLEDevice
                if not self.device:
                    self.logger.debug(
                        "Creating new RenogyBLEDevice for %s as %s",
                        service_info.address,
                        self.device_type,
                    )
                    self.device = RenogyBLEDevice(
                        service_info.device,
                        service_info.advertisement.rssi,
                        device_type=self.device_type,
                    )
                else:
                    # Store the old name to detect changes
                    old_name = self.device.name

                    self.device.ble_device = service_info.device
                    # Update name if available from service_info
                    if (
                        service_info.name
                        and service_info.name != "Unknown Renogy Device"
                    ):
                        cleaned_name = clean_device_name(service_info.name)
                        if old_name != cleaned_name:
                            self.device.name = cleaned_name
                            self.logger.debug(
                                "Updated device name from '%s' to '%s'",
                                old_name,
                                cleaned_name,
                            )

                    # Prefer the RSSI from advertisement data if available
                    self.device.rssi = (
                        service_info.advertisement.rssi
                        if service_info.advertisement
                        and service_info.advertisement.rssi is not None
                        else service_info.device.rssi
                    )

                    # Ensure device type is set correctly
                    if self.device.device_type != self.device_type:
                        self.logger.debug(
                            "Updating device type from '%s' to '%s'",
                            self.device.device_type,
                            self.device_type,
                        )
                        self.device.device_type = self.device_type

                # Dispatch to appropriate flow
                if self.device.device_type == DeviceType.SHUNT.value:
                    return await self._read_shunt_device(service_info)
                return await self._read_modbus_device(service_info)
            finally:
                self._connection_in_progress = False

    async def _read_shunt_device(self, service_info: BluetoothServiceInfoBleak) -> bool:
        """Handle reading data for SmartShunt devices via BLE notifications + manufacturer packet."""
        device = self.device
        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                service_info.device,
                device.name or device.address,
                max_attempts=3,
            )
        except BleakError as e:
            self.logger.warning(
                "BLE connection error for shunt device %s: %s", device.name, e
            )
            device.update_availability(False, e)
            self.last_update_success = False
            return False

        try:
            notification_event = asyncio.Event()
            received_packets: list[bytes] = []

            def _notif_handler(_: int, data: bytes) -> None:
                self.logger.debug("Notification received: %s", data)
                received_packets.append(data)
                notification_event.set()

            # --- Enable notifications on the correct notify characteristic ---
            NOTIFY_CHAR_UUID = RENOGY_SHUNT_NOTIFY_CHAR_UUID
            WRITE_CHAR_UUID = RENOGY_SHUNT_WRITE_CHAR_UUID
            CCCD_UUID = RENOGY_SHUNT_CCCD_UUID

            await client.start_notify(NOTIFY_CHAR_UUID, _notif_handler)
            self.logger.debug("Started notify on %s; waiting for notification...", NOTIFY_CHAR_UUID)

            # Explicitly write to CCCD to enable notifications
            try:
                char = client.services.get_characteristic(NOTIFY_CHAR_UUID)
                if char is not None and hasattr(char, "descriptors"):
                    cccd = next(
                        (d for d in char.descriptors if d.uuid.upper() == CCCD_UUID.upper()),
                        None,
                    )
                    if cccd is not None:
                        await client.write_gatt_descriptor(cccd.handle, b"\x01\x00")
                        self.logger.debug("Explicitly wrote {0x01,0x00} to CCCD for notifications")
            except Exception as e:
                self.logger.debug("Optional: Failed explicit CCCD write for notifications: %s", e)

            # Write to the paired writable characteristic to trigger notification
            try:
                await client.write_gatt_char(WRITE_CHAR_UUID, b"\x01\x00")
                self.logger.debug("Wrote b'\\x01\\x00' to %s to trigger notification", WRITE_CHAR_UUID)
            except Exception as e:
                self.logger.debug("Failed to write to %s: %s", WRITE_CHAR_UUID, e)

            # # Optional: Try reading the notify characteristic to trigger notifications
            # try:
            #     read_data = await client.read_gatt_char(NOTIFY_CHAR_UUID)
            #     self.logger.debug("Read from %s after notify: %s", NOTIFY_CHAR_UUID, read_data)
            # except Exception as e:
            #     self.logger.debug("Optional: Failed to read %s after notify: %s", NOTIFY_CHAR_UUID, e)

            try:
                await asyncio.wait_for(notification_event.wait(), MAX_NOTIFICATION_WAIT_TIME)
            except asyncio.TimeoutError:
                self.logger.warning("Timeout waiting for notification from device %s", device.name)
                return False

            await client.stop_notify(NOTIFY_CHAR_UUID)

            metrics: Dict[str, float | int | str] = {}
            for pkt in received_packets:
                try:
                    metrics.update(parse_shunt_ble_packet(pkt))
                except ValueError as parse_err:
                    self.logger.warning("Invalid SmartShunt BLE packet: %s", pkt)

            manu = service_info.advertisement.manufacturer_data.get(
                RENOGY_SHUNT_MANUF_ID, b""
            )
            try:
                metrics.update(parse_shunt_packet(bytes(manu)))
            except ValueError as manu_err:
                self.logger.warning("Invalid SmartShunt manufacturer packet: %s", manu)

            self.device.parsed_data = metrics
            self.data = dict(metrics)
            self.device.update_availability(True, None)
            self.last_update_success = True
            self.logger.debug("Parsed SmartShunt data: %s", metrics)
            return True
        except (BleakError, asyncio.TimeoutError, ValueError) as err:
            self.logger.warning("Shunt read failed: %s", err)
            self.device.update_availability(False, err)
            self.last_update_success = False
            return False
        finally:
            try:
                if client.is_connected:
                    await client.disconnect()
            except Exception as disconnect_err:
                self.logger.debug("Error during client disconnect: %s", disconnect_err)

    async def _read_modbus_device(self, service_info: BluetoothServiceInfoBleak) -> bool:
        """Handle reading data over Modbus for non-shunt devices."""
        device = self.device
        self.logger.debug(
            "Polling %s device: %s (%s)",
            device.device_type,
            device.name,
            device.address,
        )

        # Prevent overlapping connection attempts
        client = None
        try:
            client = await establish_connection(
                BleakClientWithServiceCache,
                service_info.device,
                device.name or device.address,
                max_attempts=3,
            )
        except (BleakConnectionError, BleakDBusError, BleakError) as e:
            self.logger.warning(
                "BLE connection error for device %s: %s", device.name, e
            )
            device.update_availability(False, e)
            self.last_update_success = False
            return False

        # Existing logic continues...
        any_command_succeeded = False
        try:
            self.logger.debug("Connected to device %s", device.name)

            # Create an event that will be set when notification data is received
            notification_event = asyncio.Event()
            notification_data = bytearray()

            def notification_handler(sender, data):
                notification_data.extend(data)
                notification_event.set()

            # Subscribe to Modbus read characteristic
            notify_uuid = RENOGY_READ_CHAR_UUID
            await client.start_notify(notify_uuid, notification_handler)

            # Iterate through each Modbus command defined for the
            # current device type.  All results are gathered before
            # the connection is closed.
            for cmd_name, cmd in COMMANDS[self.device_type].items():
                notification_data.clear()
                notification_event.clear()

                # Build and send the Modbus read request for this
                # command.  The helper appends the CRC bytes.
                modbus_request = ModbusUtils.create_read_request(
                    DEFAULT_DEVICE_ID, *cmd
                )
                self.logger.debug(
                    "Sending %s command: %s",
                    cmd_name,
                    list(modbus_request),
                )
                await client.write_gatt_char(
                    RENOGY_WRITE_CHAR_UUID, modbus_request
                )

                # Expected length = 3 header bytes + 2 * word_count
                # data bytes + 2 byte CRC.
                word_count = cmd[2]
                expected_len = 3 + word_count * 2 + 2
                start_time = self.hass.loop.time()

                # Wait until the entire response has been received
                # via notifications or until a timeout occurs.

                try:
                    while len(notification_data) < expected_len:
                        remaining = MAX_NOTIFICATION_WAIT_TIME - (
                            self.hass.loop.time() - start_time
                        )
                        if remaining <= 0:
                            raise asyncio.TimeoutError()
                        await asyncio.wait_for(
                            notification_event.wait(), remaining
                        )
                        notification_event.clear()
                except asyncio.TimeoutError:
                    self.logger.info(
                        "Timeout – only %s / %s bytes received for %s from device %s",
                        len(notification_data),
                        expected_len,
                        cmd_name,
                        device.name,
                    )
                    continue

                # Slice the collected notifications in case extra
                # bytes were received and pass them to the parser.
                result_data = bytes(notification_data[:expected_len])
                self.logger.debug(
                    "Received %s data length: %s (expected %s)",
                    cmd_name,
                    len(result_data),
                    expected_len,
                )

                # Parse and store the response on the device object
                cmd_success = device.update_parsed_data(
                    result_data,
                    register=cmd[1],
                    cmd_name=cmd_name,
                )

                if cmd_success:
                    # Keep track of at least one successful command
                    self.logger.debug(
                        "Successfully read and parsed %s data from device %s",
                        cmd_name,
                        device.name,
                    )
                    any_command_succeeded = True
                else:
                    self.logger.info(
                        "Failed to parse %s data from device %s",
                        cmd_name,
                        device.name,
                    )

            await client.stop_notify(notify_uuid)
            success = any_command_succeeded
            if not success:
                error = Exception("No commands completed successfully")

        except BleakError as e:
            self.logger.info(
                "BLE error with device %s: %s", device.name, str(e)
            )
            error = e
            success = False
        except Exception as e:
            self.logger.error(
                "Error reading data from device %s: %s", device.name, str(e)
            )
            error = e
            success = False
        finally:
            # BleakClientWithServiceCache handles disconnect in context manager
            # but we need to ensure the client is disconnected
            if client and client.is_connected:
                try:
                    await client.disconnect()
                    self.logger.debug(
                        "Disconnected from device %s", device.name
                    )
                except Exception as e:
                    self.logger.debug(
                        "Error disconnecting from device %s: %s",
                        device.name,
                        str(e),
                    )
                    # Don't override previous errors with disconnect errors
                    if error is None:
                        error = e

        # Always update the device availability and the coordinator's
        # success flag so entities can react appropriately.

        # Use local variables with guaranteed initialization to avoid UnboundLocalError
        final_success = locals().get('success', False)
        final_error = locals().get('error', Exception("Unknown error in _read_modbus_device"))

        try:
            device.update_availability(final_success, final_error)
            self.last_update_success = final_success
        except Exception as e:
            # Fallback if there's any issue with device availability update
            self.logger.error("Error updating device availability: %s", e)
            device.update_availability(False, Exception(f"Update error: {e}"))
            self.last_update_success = False

        # Update coordinator data if successful
        if success and device.parsed_data:
            self.data = dict(device.parsed_data)
            self.logger.debug("Updated coordinator data: %s", self.data)

        return success

    async def _async_poll(self, service_info: BluetoothServiceInfoBleak) -> None:
        """Poll the device."""
        # If a connection is already in progress, don't start another one
        if self._connection_in_progress:
            self.logger.debug("Connection already in progress, skipping poll")
            return

        self.last_poll_time = datetime.now()
        self.logger.debug(
            "Polling device: %s (%s)", service_info.name, service_info.address
        )

        # Read device data using service_info and Home Assistant's Bluetooth API
        success = await self._read_device_data(service_info)

        if success and self.device and self.device.parsed_data:
            # Log the parsed data for debugging
            self.logger.debug("Parsed data: %s", self.device.parsed_data)

            # Call the callback if available
            if self.device_data_callback:
                try:
                    await self.device_data_callback(self.device)
                except Exception as e:
                    self.logger.error("Error in device data callback: %s", str(e))

            # Update all listeners after successful data acquisition
            self.async_update_listeners()

        else:
            self.logger.info("Failed to retrieve data from %s", service_info.address)
            self.last_update_success = False
