"""Handles VPD Calculation and MQTT Publishing."""
from __future__ import annotations

import json
import logging
import math

from homeassistant.components import mqtt
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfPressure,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceRegistry, async_get as async_get_device_registry # To get device identifiers
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.typing import UndefinedType # Added

from .const import DOMAIN, MQTT_PREFIX

_LOGGER = logging.getLogger(__name__)

# MQTT Discovery settings
DISCOVERY_PAYLOAD_SCHEMA = {
    "name": None, # Set dynamically
    "state_topic": None, # Set dynamically
    "unique_id": None, # Set dynamically
    "unit_of_measurement": UnitOfPressure.KPA,
    "device_class": SensorDeviceClass.PRESSURE,
    "state_class": SensorStateClass.MEASUREMENT,
    "value_template": "{{ value }}", # Assuming direct state publishing
    "device": None, # Set dynamically with target device identifiers
    "availability_topic": None, # Set dynamically
    "payload_available": "online",
    "payload_not_available": "offline",
    "enabled_by_default": True,
}

class VPDCalculatorMqttPublisher:
    """Calculates VPD and publishes via MQTT Discovery."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the publisher."""
        self.hass = hass
        self.config_entry = config_entry
        self.config_data = config_entry.data
        self.entry_id = config_entry.entry_id

        self._name = self.config_data["name"]
        self._temp_id = self.config_data["temp_sensor"]
        self._hum_id = self.config_data["humidity_sensor"]
        self._delta = self.config_data["leaf_delta"]
        self._target_device_id = self.config_data["target_device"]

        # MQTT Topics
        self._base_topic = f"{MQTT_PREFIX}/{self.entry_id}"
        self._state_topic = f"{self._base_topic}/state"
        self._availability_topic = f"{self._base_topic}/availability"
        self._config_topic = f"homeassistant/sensor/{self.entry_id}/config" # Discovery topic

        # Unique ID for the MQTT sensor entity
        self._mqtt_unique_id = f"{self.entry_id}_vpd_mqtt"

        self._target_device_identifiers = None # Will be looked up
        self._temp_state = None
        self._hum_state = None
        self._vpd_state = None
        self._available = False
        self._listeners = [] # To store listener removal callbacks

        _LOGGER.debug("[%s] Initialized MQTT Publisher", self.entry_id)

    async def async_setup(self) -> None:
        """Set up MQTT discovery and state listeners."""
        _LOGGER.debug("[%s] Starting setup", self.entry_id)

        # 1. Get target device identifiers
        # Extract identifiers - expecting tuples like ('mqtt', 'id') or just strings
        device_ids_list = []
        for identifier in target_device.identifiers:
            if isinstance(identifier, (list, tuple)) and len(identifier) == 2:
                # If it's a tuple like ('mqtt', 'xyz'), often the second part is the key ID
                device_ids_list.append(str(identifier[1]))
            elif isinstance(identifier, str):
                # If it's already a string
                device_ids_list.append(identifier)

        if not device_ids_list:
            _LOGGER.error(
                "[%s] Could not extract usable string identifiers from target device: %s",
                self.entry_id,
                target_device.identifiers,
            )
            return # Cannot proceed

        self._target_device_identifiers_for_mqtt = device_ids_list # Store the list of strings
        _LOGGER.debug(
            "[%s] Found target device identifiers for MQTT: %s",
            self.entry_id,
            self._target_device_identifiers_for_mqtt,
        )

        # Use the first identifier set found (usually sufficient)
        self._target_device_identifiers = list(target_device.identifiers)[0]
        _LOGGER.debug(
            "[%s] Found target device identifiers: %s",
            self.entry_id,
            self._target_device_identifiers,
        )

        # 2. Construct Discovery Payload
        discovery_payload = DISCOVERY_PAYLOAD_SCHEMA.copy()
        discovery_payload["name"] = self._name
        discovery_payload["state_topic"] = self._state_topic
        discovery_payload["unique_id"] = self._mqtt_unique_id
        discovery_payload["availability_topic"] = self._availability_topic
        discovery_payload["device"] = {
            "identifiers": self._target_device_identifiers_for_mqtt # <<< Use the list of strings directly
        }

        discovery_json = json.dumps(discovery_payload)
        _LOGGER.debug("[%s] Publishing discovery to %s: %s", self.entry_id, self._config_topic, discovery_json)

        # 3. Publish Discovery Message
        await mqtt.async_publish(
            self.hass, self._config_topic, discovery_json, qos=0, retain=True # Retain config
        )

        # 4. Set up state listeners for input sensors
        self._listeners.append(
            async_track_state_change_event(
                self.hass, [self._temp_id, self._hum_id], self._handle_state_update_event
            )
        )

        # 5. Get initial states and publish first state/availability
        await self._update_initial_states()
        await self._update_and_publish() # Calculate and publish

        _LOGGER.info("[%s] Setup complete. MQTT sensor '%s' configured.", self.entry_id, self._mqtt_unique_id)


    async def _update_initial_states(self) -> None:
        """Get initial states of source sensors."""
        temp_state_obj = self.hass.states.get(self._temp_id)
        hum_state_obj = self.hass.states.get(self._hum_id)

        if temp_state_obj and temp_state_obj.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try: self._temp_state = float(temp_state_obj.state)
            except (ValueError, TypeError): self._temp_state = None
        if hum_state_obj and hum_state_obj.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try: self._hum_state = float(hum_state_obj.state)
            except (ValueError, TypeError): self._hum_state = None


    @callback
    def _handle_state_update_event(self, event: Event) -> None:
        """Handle state changes of source sensors and update."""
        new_state = event.data.get("new_state")
        entity_id = event.data.get("entity_id")
        _LOGGER.debug("[%s] State change detected for %s", self.entry_id, entity_id)

        state_value = None
        if new_state and new_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try:
                state_value = float(new_state.state)
            except (ValueError, TypeError):
                _LOGGER.warning("[%s] Could not parse state for %s: %s", self.entry_id, entity_id, new_state.state)
                state_value = None

        if entity_id == self._temp_id:
            self._temp_state = state_value
        elif entity_id == self._hum_id:
            self._hum_state = state_value

        await self._update_and_publish()


    @callback
    def async _update_and_publish(self) -> None:
        """Calculate VPD and publish state and availability via MQTT."""
        old_available = self._available
        old_vpd_state = self._vpd_state

        if self._temp_state is None or self._hum_state is None:
            self._available = False
            self._vpd_state = None
        else:
            try:
                temperature = self._temp_state
                humidity = self._hum_state
                t_leaf = temperature + self._delta
                es_leaf = 0.61078 * math.exp((17.27 * t_leaf) / (t_leaf + 237.3))
                es_air = 0.61078 * math.exp((17.27 * temperature) / (temperature + 237.3))
                ea = (humidity / 100.0) * es_air
                vpd = es_leaf - ea
                self._vpd_state = round(max(0.0, vpd), 2) # Ensure >= 0
                self._available = True
            except (ValueError, TypeError, ZeroDivisionError, OverflowError) as e:
                _LOGGER.error("[%s] Error calculating VPD: %s", self.entry_id, e)
                self._available = False
                self._vpd_state = None

        # Publish changes
        availability_changed = (old_available != self._available)
        state_changed = (self._vpd_state != old_vpd_state)

        if availability_changed:
            payload = "online" if self._available else "offline"
            _LOGGER.debug("[%s] Publishing availability to %s: %s", self.entry_id, self._availability_topic, payload)
            await mqtt.async_publish(self.hass, self._availability_topic, payload, qos=0, retain=True) # Retain availability

        # Only publish state if available and changed
        if self._available and state_changed:
            _LOGGER.debug("[%s] Publishing state to %s: %s", self.entry_id, self._state_topic, self._vpd_state)
            await mqtt.async_publish(self.hass, self._state_topic, str(self._vpd_state), qos=0, retain=True) # Retain state


    async def async_unload(self) -> bool:
        """Clean up resources."""
        _LOGGER.debug("[%s] Unloading", self.entry_id)
        # Remove MQTT discovery message
        _LOGGER.debug("[%s] Publishing empty discovery message to %s", self.entry_id, self._config_topic)
        await mqtt.async_publish(self.hass, self._config_topic, "", qos=0, retain=False)

        # Remove availability message
        _LOGGER.debug("[%s] Publishing empty availability message to %s", self.entry_id, self._availability_topic)
        await mqtt.async_publish(self.hass, self._availability_topic, "", qos=0, retain=True) # Clear retained availability

        # Stop listeners
        for remove_listener in self._listeners:
            remove_listener()
        self._listeners.clear()
        _LOGGER.info("[%s] Unload complete.", self.entry_id)
        return True