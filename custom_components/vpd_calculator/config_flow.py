"""Config flow for VPD Calculator integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

# Using OptionsFlow to allow changing settings later if needed
# And to handle conditional steps more cleanly
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow, ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_KEY_CREATE_THRESHOLDS,
    CONF_KEY_INITIAL_MIN_THRESHOLD,
    CONF_KEY_INITIAL_MAX_THRESHOLD,
    DEFAULT_MIN_THRESHOLD,
    DEFAULT_MAX_THRESHOLD,
    DEFAULT_THRESHOLD_MIN_LIMIT,
    DEFAULT_THRESHOLD_MAX_LIMIT,
    DEFAULT_THRESHOLD_STEP,
)

_LOGGER = logging.getLogger(__name__)

# --- Schema Definitions ---
STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("name"): str,
        vol.Required("temp_sensor"): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="temperature"),
        ),
        vol.Required("humidity_sensor"): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="sensor", device_class="humidity"),
        ),
        vol.Optional("leaf_delta", default=0.0): selector.NumberSelector(
            selector.NumberSelectorConfig(min=-5.0, max=5.0, step=0.1, mode="box"),
        ),
        vol.Optional("target_device"): selector.DeviceSelector(),
        vol.Optional(CONF_KEY_CREATE_THRESHOLDS, default=True): bool,
    }
)

# Schema for the optional step to set initial threshold values
STEP_THRESHOLDS_DATA_SCHEMA = vol.Schema(
     {
        vol.Optional(
            CONF_KEY_INITIAL_MIN_THRESHOLD, default=DEFAULT_MIN_THRESHOLD
        ): selector.NumberSelector(
             selector.NumberSelectorConfig(
                min=DEFAULT_THRESHOLD_MIN_LIMIT,
                max=DEFAULT_THRESHOLD_MAX_LIMIT,
                step=DEFAULT_THRESHOLD_STEP,
                mode="box"
            ),
        ),
        vol.Optional(
            CONF_KEY_INITIAL_MAX_THRESHOLD, default=DEFAULT_MAX_THRESHOLD
        ): selector.NumberSelector(
             selector.NumberSelectorConfig(
                min=DEFAULT_THRESHOLD_MIN_LIMIT,
                max=DEFAULT_THRESHOLD_MAX_LIMIT,
                step=DEFAULT_THRESHOLD_STEP,
                mode="box"
            ),
        ),
     }
)
# --- Config Flow ---
class VPDCalculatorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for VPD Calculator."""
    VERSION = 1
    # Store data between steps
    config_data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return VPDCalculatorOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step (user step)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Store initial data
            self.config_data.update(user_input)
            # Check if threshold creation is enabled
            if user_input.get(CONF_KEY_CREATE_THRESHOLDS, True):
                # If yes, proceed to the next step to set initial values
                return await self.async_step_thresholds()
            else:
                # If no, finish the flow now
                _LOGGER.info("Creating VPD Calculator entry (no thresholds): %s", self.config_data)
                return self.async_create_entry(title=self.config_data["name"], data=self.config_data)

        # Show the initial form
        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    async def async_step_thresholds(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the step to set initial threshold values."""
        errors: dict[str, str] = {}
        if user_input is not None:
            # Add threshold defaults to the main config data
            self.config_data.update(user_input)
            _LOGGER.info("Creating VPD Calculator entry (with thresholds): %s", self.config_data)
            # Validation: Ensure min is not >= max
            min_val = self.config_data.get(CONF_KEY_INITIAL_MIN_THRESHOLD, DEFAULT_MIN_THRESHOLD)
            max_val = self.config_data.get(CONF_KEY_INITIAL_MAX_THRESHOLD, DEFAULT_MAX_THRESHOLD)
            if min_val >= max_val:
                 errors["base"] = "min_max_invalid" # Error key defined in strings.json
                 # Show form again with error
                 return self.async_show_form(
                    step_id="thresholds", data_schema=STEP_THRESHOLDS_DATA_SCHEMA, errors=errors
                 )

            # Create the config entry
            return self.async_create_entry(title=self.config_data["name"], data=self.config_data)

        # Show the threshold defaults form
        return self.async_show_form(
            step_id="thresholds", data_schema=STEP_THRESHOLDS_DATA_SCHEMA, errors=errors
        )

# --- Options Flow (Example - Allows changing settings later via Configure button) ---
# This is optional but good practice if you want users to change settings later
class VPDCalculatorOptionsFlow(OptionsFlow):
    """Handle an options flow for VPD Calculator."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow."""
        # self.config_entry = config_entry
        # Store options - start with current config entry data
        self.options = dict(config_entry.data)

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the main options (similar to user step)."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self.options.update(user_input)
            # If thresholds enabled in new options, go to threshold step
            if self.options.get(CONF_KEY_CREATE_THRESHOLDS, True):
                 return await self.async_step_thresholds_options()
            else:
                 # Otherwise, save options and finish
                 return self.async_create_entry(title="", data=self.options)

        # Populate schema with current values from options
        user_schema = vol.Schema({
            vol.Required("name", default=self.options.get("name")): str,
            vol.Required("temp_sensor", default=self.options.get("temp_sensor")): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="temperature"),
            ),
            vol.Required("humidity_sensor", default=self.options.get("humidity_sensor")): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor", device_class="humidity"),
            ),
            vol.Optional("leaf_delta", default=self.options.get("leaf_delta", 0.0)): selector.NumberSelector(
                selector.NumberSelectorConfig(min=-5.0, max=5.0, step=0.1, mode="box"),
            ),
            vol.Optional("target_device", default=self.options.get("target_device")): selector.DeviceSelector(),
            vol.Optional(CONF_KEY_CREATE_THRESHOLDS, default=self.options.get(CONF_KEY_CREATE_THRESHOLDS, True)): bool,
        })

        return self.async_show_form(step_id="init", data_schema=user_schema, errors=errors)


    async def async_step_thresholds_options(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
         """Manage the threshold options step."""
         errors: dict[str, str] = {}
         if user_input is not None:
            self.options.update(user_input)
            # Validation
            min_val = self.options.get(CONF_KEY_INITIAL_MIN_THRESHOLD, DEFAULT_MIN_THRESHOLD)
            max_val = self.options.get(CONF_KEY_INITIAL_MAX_THRESHOLD, DEFAULT_MAX_THRESHOLD)
            if min_val >= max_val:
                 errors["base"] = "min_max_invalid"
                 # Show form again if error
                 threshold_schema = self._get_threshold_options_schema()
                 return self.async_show_form(step_id="thresholds_options", data_schema=threshold_schema, errors=errors)

            # Save options and finish
            return self.async_create_entry(title="", data=self.options)

         threshold_schema = self._get_threshold_options_schema()
         return self.async_show_form(step_id="thresholds_options", data_schema=threshold_schema, errors=errors)

    def _get_threshold_options_schema(self) -> vol.Schema:
         """Generate schema for threshold options step with current values."""
         return vol.Schema({
            vol.Optional(
                CONF_KEY_INITIAL_MIN_THRESHOLD,
                default=self.options.get(CONF_KEY_INITIAL_MIN_THRESHOLD, DEFAULT_MIN_THRESHOLD)
            ): selector.NumberSelector(
                 selector.NumberSelectorConfig(min=DEFAULT_THRESHOLD_MIN_LIMIT, max=DEFAULT_THRESHOLD_MAX_LIMIT, step=DEFAULT_THRESHOLD_STEP, mode="box")
            ),
            vol.Optional(
                CONF_KEY_INITIAL_MAX_THRESHOLD,
                default=self.options.get(CONF_KEY_INITIAL_MAX_THRESHOLD, DEFAULT_MAX_THRESHOLD)
            ): selector.NumberSelector(
                 selector.NumberSelectorConfig(min=DEFAULT_THRESHOLD_MIN_LIMIT, max=DEFAULT_THRESHOLD_MAX_LIMIT, step=DEFAULT_THRESHOLD_STEP, mode="box")
            ),
         })