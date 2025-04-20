"""The VPD Calculator integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
# from homeassistant.const import Platform # No longer creating platform entities directly

from .const import DOMAIN
# --- Ensure this import works ---
from .mqtt_publisher import VPDCalculatorMqttPublisher

_LOGGER = logging.getLogger(__name__)

# PLATFORMS: list[Platform] = [] # Remove platform setup

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up VPD Calculator from a config entry."""
    _LOGGER.info("Setting up VPD Calculator entry %s (MQTT)", entry.entry_id)
    try:
        # --- Instantiate the publisher ---
        publisher = VPDCalculatorMqttPublisher(hass, entry)
        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = publisher

        # --- Call its setup method ---
        await publisher.async_setup()

    except Exception as err: # Add error handling during setup
        _LOGGER.exception("Failed to set up VPD publisher for %s: %s", entry.entry_id, err)
        return False # Indicate setup failure

    return True # Indicate setup success


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading VPD Calculator entry %s (MQTT)", entry.entry_id)

    publisher = hass.data[DOMAIN].get(entry.entry_id)
    unload_ok = False
    if publisher:
        try:
            unload_ok = await publisher.async_unload() # Tell publisher to clean up
        except Exception as err: # Add error handling during unload
             _LOGGER.exception("Failed to unload VPD publisher for %s: %s", entry.entry_id, err)
             unload_ok = False # Ensure it's marked as failed

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None) # Remove from hass.data
    elif entry.entry_id in hass.data.get(DOMAIN, {}):
         # If unload failed but entry still exists in data, remove it anyway
         # to prevent issues on potential reload.
         hass.data[DOMAIN].pop(entry.entry_id, None)
         _LOGGER.warning("Force removed publisher data for %s after unload failure.", entry.entry_id)
         return False # Still report failure

    return unload_ok # Return actual unload status