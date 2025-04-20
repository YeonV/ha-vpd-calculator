"""Config flow for VPD Calculator integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
# from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Schema for the user configuration step
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("name"): str, # Name for this specific calculator instance
        vol.Required("temp_sensor"): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="temperature"),
        ),
        vol.Required("humidity_sensor"): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="humidity"),
        ),
        vol.Optional("leaf_delta", default=0.0): selector.NumberSelector( # Changed default to 0.0 as it's often negligible/unknown
            selector.NumberSelectorConfig(min=-5.0, max=5.0, step=0.1, mode="box"),
        ),
        vol.Required("target_device"): selector.DeviceSelector(),
    }
)


class VPDCalculatorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VPD Calculator."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # You could add validation here if needed
            # For example, check if temp/humidity sensors exist (though selector usually handles this)

            _LOGGER.info("Creating VPD Calculator entry with data: %s", user_input)
            # Use the user-provided name for the config entry title
            # Abort if an entry with the same name already exists? Optional.
            # await self.async_set_unique_id(user_input["name"].lower().replace(" ", "_"))
            # self._abort_if_unique_id_configured()

            return self.async_create_entry(title=user_input["name"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )