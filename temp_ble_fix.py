"""Temporary file to develop the event loop closure fixes"""

# Key fixes needed for event loop closure during shutdown:

# 1. Enhanced async_stop method with proper task cancellation
def async_stop_enhanced(self) -> None:
    """Stop polling and clean up all resources."""
    self.logger.debug("Stopping coordinator for device %s", self.address)
    
    # Mark that we're shutting down to prevent new operations
    self._connection_in_progress = False
    
    # Cancel scheduled refresh first to prevent new tasks
    if self._unsub_refresh:
        try:
            self._unsub_refresh()
        except Exception as e:
            self.logger.debug("Error canceling refresh schedule: %s", e)
        finally:
            self._unsub_refresh = None

    # Cancel any ongoing refresh task with proper exception handling
    if self._request_refresh_task and not self._request_refresh_task.done():
        try:
            self._request_refresh_task.cancel()
        except Exception as e:
            self.logger.debug("Error canceling refresh task: %s", e)
        finally:
            self._request_refresh_task = None

    # Cancel bluetooth subscriptions with error handling
    try:
        self._async_cancel_bluetooth_subscription()
    except Exception as e:
        self.logger.debug("Error canceling bluetooth subscription: %s", e)

    # Clean up listeners
    self._listeners = []

    # Call parent cleanup with comprehensive error handling
    try:
        super().async_stop()
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            self.logger.debug("Event loop already closed during shutdown - this is normal")
        else:
            self.logger.debug("RuntimeError during parent async_stop: %s", e)
    except Exception as e:
        # Log but don't raise to prevent shutdown issues
        self.logger.debug("Error during parent async_stop: %s", e)


# 2. Enhanced refresh interval handler with shutdown check
async def _handle_refresh_interval_enhanced(self, _now=None):
    """Handle a refresh interval occurring."""
    # Check if Home Assistant is shutting down before processing
    try:
        if self.hass.state not in (CoreState.starting, CoreState.running):
            self.logger.debug("Skipping refresh interval - Home Assistant is shutting down")
            return
        
        self.logger.debug("Regular interval refresh for %s", self.address)
        await self.async_request_refresh()
    except Exception as e:
        # Catch any exceptions during shutdown to prevent event loop issues
        self.logger.debug("Error during refresh interval (likely shutdown): %s", e)


# 3. Enhanced listener update with shutdown check
def async_update_listeners_enhanced(self) -> None:
    """Update all registered listeners."""
    # Don't update listeners if Home Assistant is shutting down
    if self.hass.state not in (CoreState.starting, CoreState.running):
        self.logger.debug("Skipping listener updates - Home Assistant is shutting down")
        return
        
    for update_callback in self._listeners:
        try:
            update_callback()
        except Exception as e:
            # Don't let a single listener failure crash the coordinator
            self.logger.debug("Error updating listener during shutdown: %s", e)


# 4. Enhanced _needs_poll with better shutdown handling
def _needs_poll_enhanced(self, service_info, last_poll) -> bool:
    """Determine if device needs polling based on time since last poll."""
    # Only poll if hass is running and device is connectable
    if self.hass.state not in (CoreState.starting, CoreState.running):
        self.logger.debug("Skipping poll - Home Assistant state: %s", self.hass.state)
        return False
    
    # ... rest of existing logic
    return True  # simplified for this temp file
