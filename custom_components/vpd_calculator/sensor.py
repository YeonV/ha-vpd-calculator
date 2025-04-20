"""Sensor platform for VPD Calculator."""
from __future__ import annotations

import logging
import math

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPressure, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo # Add DeviceInfo here
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the VPD sensor entry."""
    config = config_entry.data
    name = config["name"]
    temp_sensor_id = config["temp_sensor"]
    humidity_sensor_id = config["humidity_sensor"]
    leaf_delta = config["leaf_delta"]
    target_device_id = config["target_device"]

    vpd_sensor = VPDSensor(
        hass,
        config_entry.entry_id, # Use entry_id for unique base
        name,
        temp_sensor_id,
        humidity_sensor_id,
        leaf_delta,
        target_device_id,
    )

    async_add_entities([vpd_sensor])


class VPDSensor(SensorEntity):
    """Representation of a VPD Sensor."""

    _attr_device_class = SensorDeviceClass.PRESSURE
    _attr_native_unit_of_measurement = UnitOfPressure.KPA # Use const for units
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_should_poll = False  # We update based on source sensor changes

    def __init__(
        self,
        hass: HomeAssistant,
        unique_id_base: str,
        name: str,
        temp_id: str,
        hum_id: str,
        delta: float,
        target_device_id: str,
    ) -> None:
        """Initialize the sensor."""
        _LOGGER.debug(
            "Initializing VPDSensor '%s' (unique base: %s)", name, unique_id_base
        )
        _LOGGER.debug("Received target_device_id: %s", target_device_id)

        self._hass = hass
        self._temp_id = temp_id
        self._hum_id = hum_id
        self._delta = delta

        # --- Linking ---
        # This attribute tells HA to link this entity to the target device page
        self._attr_device_id = target_device_id
        _LOGGER.debug(
            "Set _attr_device_id to: %s for entity %s", self._attr_device_id, name
        )
        # --- Entity Attributes ---
        self._attr_name = name # Use the name from config flow
        self._attr_unique_id = f"{unique_id_base}_vpd" # Ensure unique ID

        # --- State ---
        self._attr_native_value = None # Current calculated state
        self._attr_available = False # Availability depends on source sensors

        # --- Store current source states ---
        self._temp_state = None
        self._hum_state = None
    @property
    def device_info(self) -> DeviceInfo:
        """Return device information specific to this instance of the calculator."""
        return DeviceInfo(
            # Link to the *config entry* that created this entity
            identifiers={(DOMAIN, self._config_entry_id)},
            # Give the virtual device representing this calculator instance a name
            name=f"VPD Calculator ({self._attr_name})",
            manufacturer="YeonV", # Or your name/handle
            entry_type="service", # Indicates it's a calculated/service entity's "device"
            model="VPD Calculator v1.0", # Optional model info
        )
    @callback
    def _handle_state_update_event(self, event: Event) -> None:
        """Handle state changes of source sensors."""
        new_state = event.data.get("new_state")
        entity_id = event.data.get("entity_id")

        if new_state is None or new_state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            if entity_id == self._temp_id:
                self._temp_state = None
            elif entity_id == self._hum_id:
                self._hum_state = None
        else:
             try:
                if entity_id == self._temp_id:
                    self._temp_state = float(new_state.state)
                elif entity_id == self._hum_id:
                    self._hum_state = float(new_state.state)
             except (ValueError, TypeError):
                # Handle cases where state is not a valid number
                _LOGGER.warning("Could not parse state for %s: %s", entity_id, new_state.state)
                if entity_id == self._temp_id:
                    self._temp_state = None
                elif entity_id == self._hum_id:
                    self._hum_state = None

        self._update_vpd_state() # Recalculate
        self.async_write_ha_state() # Update HA state machine

    @callback
    def _update_vpd_state(self) -> None:
        """Calculate the VPD state."""
        if self._temp_state is None or self._hum_state is None:
            self._attr_available = False
            self._attr_native_value = None
            return

        try:
            temperature = self._temp_state
            humidity = self._hum_state

            # --- VPD Calculation (using math.exp for e^x) ---
            # Saturation vapor pressure (es) - simplified Tetens equation
            # Using leaf temp = air temp + delta
            t_leaf = temperature + self._delta
            es_leaf = 0.61078 * math.exp((17.27 * t_leaf) / (t_leaf + 237.3))

            # Actual vapor pressure (ea)
            es_air = 0.61078 * math.exp((17.27 * temperature) / (temperature + 237.3))
            ea = (humidity / 100.0) * es_air

            vpd = es_leaf - ea

            # Ensure VPD isn't negative (can happen with negative delta or measurement errors)
            if vpd < 0:
                vpd = 0.0

            self._attr_native_value = round(vpd, 2)
            self._attr_available = True

        except (ValueError, TypeError, ZeroDivisionError) as e:
            _LOGGER.error("Error calculating VPD: %s", e)
            self._attr_available = False
            self._attr_native_value = None


    async def async_added_to_hass(self) -> None:
        """Register state change listener when added to HA."""
        # Get initial states
        temp_state_obj = self.hass.states.get(self._temp_id)
        hum_state_obj = self.hass.states.get(self._hum_id)

        if temp_state_obj and temp_state_obj.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                self._temp_state = float(temp_state_obj.state)
            except (ValueError, TypeError):
                self._temp_state = None
        if hum_state_obj and hum_state_obj.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                self._hum_state = float(hum_state_obj.state)
            except (ValueError, TypeError):
                self._hum_state = None

        # Calculate initial state
        self._update_vpd_state()

        # Subscribe to state changes of source sensors
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._temp_id, self._hum_id], self._handle_state_update_event
            )
        )

    async def async_will_remove_from_hass(self) -> None:
        """Clean up listeners."""
        # async_on_remove handles cleanup of listeners automatically
        pass