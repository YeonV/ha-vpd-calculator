# /config/custom_components/vpd_calculator/mqtt_publisher.py

"""Handles VPD Calculation and MQTT Publishing for Sensor and Optional Thresholds."""
from __future__ import annotations

import json
import logging
import math
from typing import Any # Added

from homeassistant.components import mqtt
# from homeassistant.components.mqtt.models import MqttMessage # Removed import
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.components.number import (
    NumberDeviceClass,
    NumberMode,
)
from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfPressure,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceRegistry, async_get as async_get_device_registry
from homeassistant.helpers.event import async_track_state_change_event
# from homeassistant.helpers.restore_state import RestoreEntity # Not using yet

from .const import DOMAIN, MQTT_PREFIX

_LOGGER = logging.getLogger(__name__)

# --- Constants for Thresholds ---
CONF_KEY_LOW_THRESHOLD = "low_threshold"
CONF_KEY_HIGH_THRESHOLD = "high_threshold"
CONF_KEY_CREATE_THRESHOLDS = "create_threshold_entities" # Key for the toggle
DEFAULT_LOW_THRESHOLD = 0.8
DEFAULT_HIGH_THRESHOLD = 1.2
DEFAULT_THRESHOLD_MIN = 0.1
DEFAULT_THRESHOLD_MAX = 2.5
DEFAULT_THRESHOLD_STEP = 0.05
# -----------------------------

# --- Default Device Info (if target_device not provided) ---
DEFAULT_DEVICE_INFO = {
    "identifiers": ["yz_smartgrow"], # Must be a list
    "name": "Smart Growing",
    "model": "Blade: YZ-1",
    "manufacturer": "Yeon",
    "sw_version": "1.0.0",
    "configuration_url": "https://yeonv.com",
}
# ---------------------------------------------------------

# MQTT Discovery settings - Sensor
DISCOVERY_PAYLOAD_SENSOR_SCHEMA = {
    # ... (same as before) ...
    "name": None,
    "state_topic": None,
    "unique_id": None,
    "unit_of_measurement": UnitOfPressure.KPA,
    "device_class": SensorDeviceClass.PRESSURE,
    "state_class": SensorStateClass.MEASUREMENT,
    "value_template": "{{ value }}",
    "device": None, # Populated dynamically
    "availability_topic": None,
    "payload_available": "online",
    "payload_not_available": "offline",
    "enabled_by_default": True,
}

# MQTT Discovery settings - Number
DISCOVERY_PAYLOAD_NUMBER_SCHEMA = {
    # ... (same as before) ...
    "name": None,
    "state_topic": None,
    "command_topic": None,
    "unique_id": None,
    "unit_of_measurement": UnitOfPressure.KPA,
    "device": None, # Populated dynamically
    "availability_topic": None,
    "payload_available": "online",
    "payload_not_available": "offline",
    "min": DEFAULT_THRESHOLD_MIN,
    "max": DEFAULT_THRESHOLD_MAX,
    "step": DEFAULT_THRESHOLD_STEP,
    "mode": NumberMode.SLIDER,
    "enabled_by_default": True,
}


class VPDCalculatorMqttPublisher:
    """Calculates VPD and publishes sensor and optional number entities via MQTT Discovery."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the publisher."""
        self.hass = hass
        self.config_entry = config_entry
        self.config_data = dict(config_entry.data)
        self.entry_id = config_entry.entry_id

        self._name = self.config_data["name"]
        self._temp_id = self.config_data["temp_sensor"]
        self._hum_id = self.config_data["humidity_sensor"]
        self._delta = self.config_data["leaf_delta"]
        # --- Get optional values ---
        self._target_device_id = self.config_data.get("target_device") # Returns None if not present
        self._create_threshold_entities = self.config_data.get(CONF_KEY_CREATE_THRESHOLDS, True) # Default true
        # -------------------------

        # Internal State for Thresholds (initialize even if not created, simplifies logic)
        self._low_threshold = self.config_data.get(CONF_KEY_LOW_THRESHOLD, DEFAULT_LOW_THRESHOLD)
        self._high_threshold = self.config_data.get(CONF_KEY_HIGH_THRESHOLD, DEFAULT_HIGH_THRESHOLD)

        # MQTT Topics - Sensor (same as before)
        self._base_topic = f"{MQTT_PREFIX}/{self.entry_id}"
        self._sensor_state_topic = f"{self._base_topic}/state"
        self._sensor_availability_topic = f"{self._base_topic}/availability" # Shared availability
        self._sensor_config_topic = f"homeassistant/sensor/{self.entry_id}/config"
        self._sensor_mqtt_unique_id = f"{self.entry_id}_vpd_mqtt"

        # MQTT Topics - Threshold Numbers (defined even if not created)
        self._low_thresh_state_topic = f"{self._base_topic}/low_threshold/state"
        self._low_thresh_command_topic = f"{self._base_topic}/low_threshold/set"
        self._low_thresh_config_topic = f"homeassistant/number/{self.entry_id}_low/config"
        self._low_thresh_mqtt_unique_id = f"{self.entry_id}_vpd_low_thresh_mqtt"
        self._high_thresh_state_topic = f"{self._base_topic}/high_threshold/state"
        self._high_thresh_command_topic = f"{self._base_topic}/high_threshold/set"
        self._high_thresh_config_topic = f"homeassistant/number/{self.entry_id}_high/config"
        self._high_thresh_mqtt_unique_id = f"{self.entry_id}_vpd_high_thresh_mqtt"

        # Common State
        self._device_block_for_mqtt = None # Will be determined in setup
        self._temp_state = None
        self._hum_state = None
        self._vpd_state = None
        self._available = False
        self._listeners = []

        _LOGGER.debug("[%s] Initialized MQTT Publisher (Thresholds: %s)", self.entry_id, self._create_threshold_entities)

    async def async_setup(self) -> None:
        """Set up MQTT discovery (sensor & optional numbers) and state listeners."""
        _LOGGER.debug("[%s] Starting setup", self.entry_id)

        # 1. Determine Device Info for MQTT Discovery
        device_block = None
        if self._target_device_id:
            # User selected a target device
            dev_reg: DeviceRegistry = async_get_device_registry(self.hass)
            target_device = dev_reg.async_get(self._target_device_id)
            if not target_device:
                _LOGGER.error("[%s] Selected target device ID '%s' not found.", self.entry_id, self._target_device_id)
                return # Cannot proceed
            # Extract identifiers
            device_ids_list = []
            for identifier in target_device.identifiers:
                 if isinstance(identifier, (list, tuple)) and len(identifier) >= 1:
                    id_str = str(identifier[1]) if len(identifier) > 1 else str(identifier[0])
                    device_ids_list.append(id_str)
                 elif isinstance(identifier, str):
                    device_ids_list.append(identifier)
            if not device_ids_list:
                 _LOGGER.error("[%s] Could not extract usable identifiers from selected device: %s", self.entry_id, target_device.identifiers)
                 return
            device_block = {"identifiers": device_ids_list}
            _LOGGER.debug("[%s] Using identifiers from selected target device: %s", self.entry_id, device_ids_list)
        else:
            # No target device selected, use default "Smart Growing" info
            device_block = DEFAULT_DEVICE_INFO.copy() # Use a copy
            # Ensure identifiers is a list for consistency, even if only one
            device_block["identifiers"] = list(device_block["identifiers"])
            _LOGGER.debug("[%s] No target device selected, using default device info.", self.entry_id)

        self._device_block_for_mqtt = device_block # Store for later use if needed

        # 2. Publish Discovery - VPD Sensor (Always publish sensor)
        sensor_payload = DISCOVERY_PAYLOAD_SENSOR_SCHEMA.copy()
        sensor_payload["name"] = self._name
        sensor_payload["state_topic"] = self._sensor_state_topic
        sensor_payload["unique_id"] = self._sensor_mqtt_unique_id
        sensor_payload["availability_topic"] = self._sensor_availability_topic
        sensor_payload["device"] = self._device_block_for_mqtt # Use determined device block
        await self._publish_discovery(self._sensor_config_topic, sensor_payload)

        # 3. Publish Discovery & Setup - Threshold Numbers (Conditional)
        if self._create_threshold_entities:
            _LOGGER.debug("[%s] Creating threshold number entities via MQTT discovery.", self.entry_id)
            # Low Threshold Number
            low_thresh_payload = DISCOVERY_PAYLOAD_NUMBER_SCHEMA.copy()
            low_thresh_payload["name"] = f"{self._name} Low Threshold"
            low_thresh_payload["state_topic"] = self._low_thresh_state_topic
            low_thresh_payload["command_topic"] = self._low_thresh_command_topic
            low_thresh_payload["unique_id"] = self._low_thresh_mqtt_unique_id
            low_thresh_payload["availability_topic"] = self._sensor_availability_topic
            low_thresh_payload["device"] = self._device_block_for_mqtt
            await self._publish_discovery(self._low_thresh_config_topic, low_thresh_payload)

            # High Threshold Number
            high_thresh_payload = DISCOVERY_PAYLOAD_NUMBER_SCHEMA.copy()
            high_thresh_payload["name"] = f"{self._name} High Threshold"
            high_thresh_payload["state_topic"] = self._high_thresh_state_topic
            high_thresh_payload["command_topic"] = self._high_thresh_command_topic
            high_thresh_payload["unique_id"] = self._high_thresh_mqtt_unique_id
            high_thresh_payload["availability_topic"] = self._sensor_availability_topic
            high_thresh_payload["device"] = self._device_block_for_mqtt
            await self._publish_discovery(self._high_thresh_config_topic, high_thresh_payload)

            # Subscribe to Command Topics for Numbers
            self._listeners.append(
                await mqtt.async_subscribe(
                    self.hass, self._low_thresh_command_topic, self._handle_low_threshold_command
                )
            )
            self._listeners.append(
                await mqtt.async_subscribe(
                    self.hass, self._high_thresh_command_topic, self._handle_high_threshold_command
                )
            )
            # Publish initial threshold states
            await self._publish_threshold_state(self._low_thresh_state_topic, self._low_threshold)
            await self._publish_threshold_state(self._high_thresh_state_topic, self._high_threshold)
        else:
             _LOGGER.debug("[%s] Skipping threshold number entity creation.", self.entry_id)


        # 4. Set up state listeners for input sensors (Always needed)
        self._listeners.append(
            async_track_state_change_event(
                self.hass, [self._temp_id, self._hum_id], self._handle_state_update_event
            )
        )

        # 5. Get initial states and publish first state/availability (Always needed)
        self._update_initial_states()
        await self._update_and_publish_vpd() # Calculate and publish initial VPD & availability

        _LOGGER.info("[%s] Setup complete. MQTT entities configured (Thresholds: %s).", self.entry_id, self._create_threshold_entities)

    # --- Helper Methods (_publish_discovery, _publish_threshold_state remain the same) ---
    async def _publish_discovery(self, config_topic: str, payload: dict) -> None:
        """Publish an MQTT discovery message."""
        discovery_json = json.dumps(payload)
        _LOGGER.debug("[%s] Publishing discovery to %s: %s", self.entry_id, config_topic, discovery_json)
        await mqtt.async_publish(self.hass, config_topic, discovery_json, qos=0, retain=True)

    async def _publish_threshold_state(self, topic: str, value: float) -> None:
        """Publish the state for a threshold number."""
        # Only publish if thresholds are enabled for this instance
        if self._create_threshold_entities:
            _LOGGER.debug("[%s] Publishing threshold state to %s: %s", self.entry_id, topic, value)
            await mqtt.async_publish(self.hass, topic, str(value), qos=0, retain=True)

    # --- Command Handlers for Numbers (Only called if subscribed) ---
    @callback
    async def _handle_low_threshold_command(self, msg: Any) -> None:
        """Handle new low threshold value from MQTT command topic."""
        await self._handle_threshold_command(
            msg, CONF_KEY_LOW_THRESHOLD, self._low_thresh_state_topic, DEFAULT_LOW_THRESHOLD
        )

    @callback
    async def _handle_high_threshold_command(self, msg: Any) -> None:
        """Handle new high threshold value from MQTT command topic."""
        await self._handle_threshold_command(
            msg, CONF_KEY_HIGH_THRESHOLD, self._high_thresh_state_topic, DEFAULT_HIGH_THRESHOLD
        )

    async def _handle_threshold_command(
        self, msg: Any, conf_key: str, state_topic: str, default_value: float
    ) -> None:
        """Generic handler for threshold command messages."""
        # (Logic remains the same - validate, update internal, persist, publish back)
        try:
            payload_str = msg.payload.decode("utf-8")
            new_value = float(payload_str)
            min_val = DISCOVERY_PAYLOAD_NUMBER_SCHEMA["min"]
            max_val = DISCOVERY_PAYLOAD_NUMBER_SCHEMA["max"]
            if not (min_val <= new_value <= max_val):
                raise ValueError(f"Value {new_value} outside range [{min_val}-{max_val}]")

            _LOGGER.debug("[%s] Received threshold command for %s: %s", self.entry_id, conf_key, new_value)

            if conf_key == CONF_KEY_LOW_THRESHOLD:
                self._low_threshold = new_value
            elif conf_key == CONF_KEY_HIGH_THRESHOLD:
                self._high_threshold = new_value

            # Persist change in config entry data
            self.config_data[conf_key] = new_value
            self.hass.config_entries.async_update_entry(self.config_entry, data=self.config_data)

            await self._publish_threshold_state(state_topic, new_value)
        except ValueError as e:
            _LOGGER.error("[%s] Invalid threshold value on %s: '%s'. Error: %s", self.entry_id, msg.topic, msg.payload, e)
        except Exception as e:
             _LOGGER.exception("[%s] Error handling threshold command on %s: %s", self.entry_id, msg.topic, e)

     # --- VPD Sensor State Update Logic ---
    def _update_initial_states(self) -> None:
        """Get initial states of source sensors."""
        # (Same as before)
        temp_state_obj = self.hass.states.get(self._temp_id)
        hum_state_obj = self.hass.states.get(self._hum_id)
        self._temp_state = None
        self._hum_state = None
        if temp_state_obj and temp_state_obj.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try: self._temp_state = float(temp_state_obj.state)
            except (ValueError, TypeError): pass
        if hum_state_obj and hum_state_obj.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try: self._hum_state = float(hum_state_obj.state)
            except (ValueError, TypeError): pass

    @callback
    def _handle_state_update_event(self, event: Event) -> None:
        """Handle state changes of source sensors and schedule VPD update."""
        # (Modified slightly to only schedule VPD update)
        new_state = event.data.get("new_state")
        entity_id = event.data.get("entity_id")
        _LOGGER.debug("[%s] State change detected for %s", self.entry_id, entity_id)

        state_value = None
        if new_state and new_state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            try: state_value = float(new_state.state)
            except (ValueError, TypeError): state_value = None

        needs_update = False
        if entity_id == self._temp_id and state_value != self._temp_state:
            self._temp_state = state_value
            needs_update = True
        elif entity_id == self._hum_id and state_value != self._hum_state:
            self._hum_state = state_value
            needs_update = True

        if needs_update:
            self.hass.async_create_task(self._update_and_publish_vpd())

    async def _update_and_publish_vpd(self) -> None:
        """Calculate VPD and publish state and availability via MQTT."""
        # (Same calculation logic as before)
        old_available = self._available
        old_vpd_state = self._vpd_state

        if self._temp_state is None or self._hum_state is None:
            self._available = False
            self._vpd_state = None
        else:
            # ... (VPD calculation) ...
            try:
                temperature = self._temp_state
                humidity = self._hum_state
                t_leaf = temperature + self._delta
                es_leaf = 0.61078 * math.exp((17.27 * t_leaf) / (t_leaf + 237.3))
                es_air = 0.61078 * math.exp((17.27 * temperature) / (temperature + 237.3))
                ea = (humidity / 100.0) * es_air
                vpd = es_leaf - ea
                self._vpd_state = round(max(0.0, vpd), 2)
                self._available = True
            except Exception as e:
                _LOGGER.error("[%s] Error calculating VPD: %s", self.entry_id, e)
                self._available = False
                self._vpd_state = None

        availability_changed = (old_available != self._available)
        state_changed = (self._vpd_state != old_vpd_state) or (availability_changed and self._available)

        # Publish availability change (applies to sensor and numbers)
        if availability_changed:
            payload = "online" if self._available else "offline"
            _LOGGER.debug("[%s] Publishing availability to %s: %s", self.entry_id, self._sensor_availability_topic, payload)
            await mqtt.async_publish(self.hass, self._sensor_availability_topic, payload, qos=0, retain=True)

        # Publish VPD sensor state change
        if self._available and state_changed:
            _LOGGER.debug("[%s] Publishing VPD state to %s: %s", self.entry_id, self._sensor_state_topic, self._vpd_state)
            await mqtt.async_publish(self.hass, self._sensor_state_topic, str(self._vpd_state), qos=0, retain=True)


    # --- Unload Logic ---
    async def async_unload(self) -> bool:
        """Clean up resources."""
        _LOGGER.debug("[%s] Unloading", self.entry_id)

        # Publish empty discovery messages for all entities that *might* have been created
        await mqtt.async_publish(self.hass, self._sensor_config_topic, "", qos=0, retain=False)
        if self._create_threshold_entities: # Only clear number discovery if they were created
             await mqtt.async_publish(self.hass, self._low_thresh_config_topic, "", qos=0, retain=False)
             await mqtt.async_publish(self.hass, self._high_thresh_config_topic, "", qos=0, retain=False)

        # Clear retained availability message (always clear this)
        await mqtt.async_publish(self.hass, self._sensor_availability_topic, "", qos=0, retain=True)

        # Stop listeners (includes MQTT subscriptions which were conditional)
        # Unsubscribing non-existent listeners is safe
        for remove_listener in self._listeners:
            try:
                remove_listener()
            except Exception as e:
                _LOGGER.warning("[%s] Error removing listener during unload: %s", self.entry_id, e)
        self._listeners.clear()

        _LOGGER.info("[%s] Unload complete.", self.entry_id)
        return True