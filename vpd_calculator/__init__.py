"""The VPD Calculator integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Define the platform this integration creates entities for
PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up VPD Calculator from a config entry."""
    _LOGGER.info("Setting up VPD Calculator entry %s", entry.entry_id)

    # Store the config entry data in hass.data if needed by platforms
    # hass.data.setdefault(DOMAIN, {})[entry.entry_id] = entry.data

    # Forward the setup to the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.info("Unloading VPD Calculator entry %s", entry.entry_id)

    # Forward the unload to the sensor platform
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Clean up hass.data if you stored anything
    # if unload_ok:
    #     hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok