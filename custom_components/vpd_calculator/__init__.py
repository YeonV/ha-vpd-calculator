# TEMPORARY TEST __init__.py
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.error("!!! TEST: async_setup_entry in vpd_calculator WAS CALLED !!!")
    # Don't actually set anything up, just prove it runs
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.error("!!! TEST: async_unload_entry in vpd_calculator WAS CALLED !!!")
    return True