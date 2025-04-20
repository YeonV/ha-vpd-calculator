"""The VPD Calculator integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
# from homeassistant.const import Platform

from .const import DOMAIN
from .mqtt_publisher import VPDCalculatorMqttPublisher

_LOGGER = logging.getLogger(__name__)

# Define the platform this integration creates entities for
# PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up VPD Calculator from a config entry."""
    _LOGGER.info("Setting up VPD Calculator entry %s (MQTT)", entry.entry_id)

    # Create and store the publisher instance for this entry
    publisher = VPDCalculatorMqttPublisher(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = publisher

    # Start the publisher's setup (MQTT discovery, listeners)
    await publisher.async_setup()

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading VPD Calculator entry %s (MQTT)", entry.entry_id)

    publisher = hass.data[DOMAIN].get(entry.entry_id)
    unload_ok = False
    if publisher:
        unload_ok = await publisher.async_unload() # Tell publisher to clean up

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None) # Remove from hass.data

    return unload_ok