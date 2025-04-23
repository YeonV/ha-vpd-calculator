# /config/custom_components/vpd_calculator/device_automation.py

"""Provides device automations for VPD Calculator."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.device_registry import DeviceEntry # Added

from .const import DOMAIN, CONF_KEY_CREATE_THRESHOLDS # Import needed consts

# --- Suggested Dashboard Config ---

async def async_get_suggested_dashboard_config(
    hass: HomeAssistant, config_entry: ConfigEntry, device: DeviceEntry
) -> dict | None:
    """Return suggested dashboard card config for the device."""

    # Only suggest if threshold entities are enabled for this instance
    if not config_entry.data.get(CONF_KEY_CREATE_THRESHOLDS, True):
        return None

    # Construct entity IDs based on config entry ID
    entry_id = config_entry.entry_id
    vpd_sensor_entity_id = f"sensor.{DOMAIN}_{entry_id}_vpd_mqtt" # Assuming sensor platform adds domain prefix
    min_thresh_entity_id = f"number.{DOMAIN}_{entry_id}_vpd_min_mqtt"
    max_thresh_entity_id = f"number.{DOMAIN}_{entry_id}_vpd_max_mqtt"

    # Check if MQTT integration added a prefix to the entity_id (it often does based on name)
    # We need the *actual* entity IDs. This part is tricky without querying the registry.
    # Let's assume the unique_id based derivation works for now, but this might need refinement.
    # A safer way might be to look up entities linked to the config entry ID.

    # Construct the Gauge card configuration dictionary
    gauge_card_config = {
        "type": "gauge",
        "name": config_entry.data.get("name", "VPD"), # Use name from config
        "entity": vpd_sensor_entity_id, # Use derived sensor entity ID
        "unit": "kPa",
        "min": 0.2, # Or use DEFAULT_THRESHOLD_MIN_LIMIT
        "max": 2.0, # Or use DEFAULT_THRESHOLD_MAX_LIMIT
        "severity": {
            "red": max_thresh_entity_id,    # Use derived max entity ID
            "green": min_thresh_entity_id,  # Use derived min entity ID
            "yellow": 0                     # Or use DEFAULT_THRESHOLD_MIN_LIMIT
        },
    }

    # Return the config wrapped in a basic structure HA expects
    return {
        "entities": [
            vpd_sensor_entity_id,
            min_thresh_entity_id,
            max_thresh_entity_id,
        ], # List entities used
        "config": gauge_card_config # The actual card config
    }

# --- Placeholder for Device Triggers/Conditions/Actions (if needed later) ---

# async def async_get_device_automations(
#     hass: HomeAssistant, device_id: str, automation_type: str
# ) -> list[dict[str, Any]]:
#     """Get device automations."""
#     # Return empty list if no specific triggers/conditions/actions are provided
#     return []