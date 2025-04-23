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

from .const import (
    DOMAIN,
    MQTT_PREFIX,
    CONF_KEY_MIN_THRESHOLD, 
    CONF_KEY_MAX_THRESHOLD, 
    CONF_KEY_INITIAL_MIN_THRESHOLD,
    CONF_KEY_INITIAL_MAX_THRESHOLD,
    CONF_KEY_CREATE_THRESHOLDS,
    DEFAULT_MIN_THRESHOLD,
    DEFAULT_MAX_THRESHOLD,
    DEFAULT_THRESHOLD_MIN_LIMIT,
    DEFAULT_THRESHOLD_MAX_LIMIT,
    DEFAULT_THRESHOLD_STEP,
)

_LOGGER = logging.getLogger(__name__)


# --- Default Device Info (if target_device not provided) ---
DEFAULT_DEVICE_INFO = {
    "identifiers": ["yz_smartgrow"],
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
    "min": DEFAULT_THRESHOLD_MIN_LIMIT,
    "max": DEFAULT_THRESHOLD_MAX_LIMIT,
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
        self.config_data = dict(config_entry.data) # Use mutable copy
        self.entry_id = config_entry.entry_id

        self._name = self.config_data["name"]
        self._temp_id = self.config_data["temp_sensor"]
        self._hum_id = self.config_data["humidity_sensor"]
        self._delta = self.config_data["leaf_delta"]
        self._target_device_id = self.config_data.get("target_device")
        self._create_threshold_entities = self.config_data.get(CONF_KEY_CREATE_THRESHOLDS, True)

        # --- Internal State for Thresholds ---
        # Use initial values from config flow if present, else defaults
        self._min_threshold = self.config_data.get(CONF_KEY_INITIAL_MIN_THRESHOLD, DEFAULT_MIN_THRESHOLD)
        self._max_threshold = self.config_data.get(CONF_KEY_INITIAL_MAX_THRESHOLD, DEFAULT_MAX_THRESHOLD)
        # Store the *actual current* values (which might differ from initial if changed via MQTT)
        # For persistence across restarts without full config entry saving on every MQTT command,
        # we'd ideally use RestoreEntity, but let's stick to saving to config entry for now.
        # Load the *last known* values if they exist in the persistent data
        self._min_threshold = self.config_data.get(CONF_KEY_MIN_THRESHOLD, self._min_threshold)
        self._max_threshold = self.config_data.get(CONF_KEY_MAX_THRESHOLD, self._max_threshold)
        # ------------------------------------

        # MQTT Topics - Sensor (same)
        self._base_topic = f"{MQTT_PREFIX}/{self.entry_id}"
        self._sensor_state_topic = f"{self._base_topic}/state"
        self._sensor_availability_topic = f"{self._base_topic}/availability"
        self._sensor_config_topic = f"homeassistant/sensor/{self.entry_id}/config"
        self._sensor_mqtt_unique_id = f"{self.entry_id}_vpd_mqtt"

        # MQTT Topics - Renamed Threshold Numbers
        self._min_thresh_state_topic = f"{self._base_topic}/min_vpd/state" 
        self._min_thresh_command_topic = f"{self._base_topic}/min_vpd/set" 
        self._min_thresh_config_topic = f"homeassistant/number/{self.entry_id}_min/config"
        self._min_thresh_mqtt_unique_id = f"{self.entry_id}_vpd_min_mqtt" 

        self._max_thresh_state_topic = f"{self._base_topic}/max_vpd/state" 
        self._max_thresh_command_topic = f"{self._base_topic}/max_vpd/set" 
        self._max_thresh_config_topic = f"homeassistant/number/{self.entry_id}_max/config"
        self._max_thresh_mqtt_unique_id = f"{self.entry_id}_vpd_max_mqtt" 

        # Common State (same)
        self._device_block_for_mqtt = None
        self._temp_state = None
        self._hum_state = None
        self._vpd_state = None
        self._available = False
        self._listeners = []

        _LOGGER.debug("[%s] Initialized MQTT Publisher (Thresholds: %s, Min: %s, Max: %s)",
                      self.entry_id, self._create_threshold_entities, self._min_threshold, self._max_threshold)


    async def async_setup(self) -> None:
        """Set up MQTT discovery (sensor & optional numbers) and state listeners."""
        _LOGGER.debug("[%s] Starting setup", self.entry_id)

        # 1. Determine Device Info for MQTT Discovery (Same as before)
        # ... (code to determine self._device_block_for_mqtt) ...
        device_block = None
        if self._target_device_id:
            dev_reg: DeviceRegistry = async_get_device_registry(self.hass)
            target_device = dev_reg.async_get(self._target_device_id)
            if not target_device: _LOGGER.error(...); return
            device_ids_list = []
            for identifier in target_device.identifiers:
                 if isinstance(identifier, (list, tuple)) and len(identifier) >= 1:
                    id_str = str(identifier[1]) if len(identifier) > 1 else str(identifier[0])
                    device_ids_list.append(id_str)
                 elif isinstance(identifier, str): device_ids_list.append(identifier)
            if not device_ids_list: _LOGGER.error(...); return
            device_block = {"identifiers": device_ids_list}
            _LOGGER.debug("[%s] Using identifiers from selected target device: %s", self.entry_id, device_ids_list)
        else:
            device_block = DEFAULT_DEVICE_INFO.copy()
            device_block["identifiers"] = list(device_block["identifiers"])
            _LOGGER.debug("[%s] No target device selected, using default device info.", self.entry_id)
        self._device_block_for_mqtt = device_block


        # 2. Publish Discovery - VPD Sensor (Same as before)
        sensor_payload = DISCOVERY_PAYLOAD_SENSOR_SCHEMA.copy()
        sensor_payload["name"] = self._name
        sensor_payload["state_topic"] = self._sensor_state_topic
        sensor_payload["unique_id"] = self._sensor_mqtt_unique_id
        sensor_payload["availability_topic"] = self._sensor_availability_topic
        sensor_payload["device"] = self._device_block_for_mqtt
        await self._publish_discovery(self._sensor_config_topic, sensor_payload)

        # 3. Publish Discovery & Setup - Threshold Numbers (Conditional)
        if self._create_threshold_entities:
            _LOGGER.debug("[%s] Creating threshold number entities via MQTT discovery.", self.entry_id)
            # Min Threshold Number (Renamed)
            min_thresh_payload = DISCOVERY_PAYLOAD_NUMBER_SCHEMA.copy()
            min_thresh_payload["name"] = f"{self._name} Min" 
            min_thresh_payload["state_topic"] = self._min_thresh_state_topic
            min_thresh_payload["command_topic"] = self._min_thresh_command_topic
            min_thresh_payload["unique_id"] = self._min_thresh_mqtt_unique_id
            min_thresh_payload["availability_topic"] = self._sensor_availability_topic
            min_thresh_payload["device"] = self._device_block_for_mqtt
            await self._publish_discovery(self._min_thresh_config_topic, min_thresh_payload)

            # Max Threshold Number (Renamed)
            max_thresh_payload = DISCOVERY_PAYLOAD_NUMBER_SCHEMA.copy()
            max_thresh_payload["name"] = f"{self._name} Max" 
            max_thresh_payload["state_topic"] = self._max_thresh_state_topic
            max_thresh_payload["command_topic"] = self._max_thresh_command_topic
            max_thresh_payload["unique_id"] = self._max_thresh_mqtt_unique_id
            max_thresh_payload["availability_topic"] = self._sensor_availability_topic
            max_thresh_payload["device"] = self._device_block_for_mqtt
            await self._publish_discovery(self._max_thresh_config_topic, max_thresh_payload)

            # Subscribe to Command Topics for Numbers
            self._listeners.append(
                await mqtt.async_subscribe(
                    self.hass, self._min_thresh_command_topic, self._handle_min_threshold_command 
                )
            )
            self._listeners.append(
                await mqtt.async_subscribe(
                    self.hass, self._max_thresh_command_topic, self._handle_max_threshold_command 
                )
            )
            # Publish initial threshold states
            await self._publish_threshold_state(self._min_thresh_state_topic, self._min_threshold)
            await self._publish_threshold_state(self._max_thresh_state_topic, self._max_threshold)
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
        await self._update_and_publish_vpd()

        _LOGGER.info("[%s] Setup complete. MQTT entities configured (Thresholds: %s).", self.entry_id, self._create_threshold_entities)


    # --- Helper Methods (_publish_discovery, _publish_threshold_state same) ---
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

    @callback
    async def _handle_min_threshold_command(self, msg: Any) -> None: 
        """Handle new min threshold value from MQTT command topic."""
        await self._handle_threshold_command(
            msg, CONF_KEY_MIN_THRESHOLD, self._min_thresh_state_topic, DEFAULT_MIN_THRESHOLD
        )

    #fuck you
    @callback
    async def _handle_max_threshold_command(self, msg: Any) -> None: 
        """Handle new max threshold value from MQTT command topic."""
        await self._handle_threshold_command(
            msg, CONF_KEY_MAX_THRESHOLD, self._max_thresh_state_topic, DEFAULT_MAX_THRESHOLD
        )

    async def _handle_threshold_command(
        self, msg: Any, conf_key: str, state_topic: str, default_value: float # Default not really used here now
    ) -> None:
        """Generic handler for threshold command messages."""
        # --- Use Renamed Keys ---
        try:
            payload_str = msg.payload # .decode("utf-8")
            new_value = float(payload_str)
            min_val = DISCOVERY_PAYLOAD_NUMBER_SCHEMA["min"]
            max_val = DISCOVERY_PAYLOAD_NUMBER_SCHEMA["max"]
            if not (min_val <= new_value <= max_val):
                raise ValueError(f"Value {new_value} outside range [{min_val}-{max_val}]")

            _LOGGER.debug("[%s] Received threshold command for %s: %s", self.entry_id, conf_key, new_value)

            # Update internal state variable based on conf_key
            if conf_key == CONF_KEY_MIN_THRESHOLD:
                 # Validation: Ensure new min isn't >= current max
                 if new_value >= self._max_threshold:
                      _LOGGER.warning("[%s] New Min VPD (%s) cannot be >= Max VPD (%s). Ignoring.", self.entry_id, new_value, self._max_threshold)
                      # Optionally publish the *old* state back to prevent UI flicker
                      await self._publish_threshold_state(state_topic, self._min_threshold)
                      return
                 self._min_threshold = new_value
            elif conf_key == CONF_KEY_MAX_THRESHOLD:
                 # Validation: Ensure new max isn't <= current min
                 if new_value <= self._min_threshold:
                      _LOGGER.warning("[%s] New Max VPD (%s) cannot be <= Min VPD (%s). Ignoring.", self.entry_id, new_value, self._min_threshold)
                      await self._publish_threshold_state(state_topic, self._max_threshold)
                      return
                 self._max_threshold = new_value

            # Persist change in config entry data
            self.config_data[conf_key] = new_value
            self.hass.config_entries.async_update_entry(self.config_entry, data=self.config_data)

            # Publish the validated state back to MQTT state topic
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
             await mqtt.async_publish(self.hass, self._min_thresh_config_topic, "", qos=0, retain=False) # Use renamed topic
             await mqtt.async_publish(self.hass, self._max_thresh_config_topic, "", qos=0, retain=False) # Use renamed topic

        # Clear retained availability message (always clear this)
        await mqtt.async_publish(self.hass, self._sensor_availability_topic, "", qos=0, retain=True)

        # Stop listeners (includes MQTT subscriptions which were conditional)
        for remove_listener in self._listeners:
            try: remove_listener()
            except Exception as e: _LOGGER.warning(...)
        self._listeners.clear()

        _LOGGER.info("[%s] Unload complete.", self.entry_id)
        return True
