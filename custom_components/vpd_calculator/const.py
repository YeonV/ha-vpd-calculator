"""Constants for the VPD Calculator integration."""

DOMAIN = "vpd_calculator"
MQTT_PREFIX = DOMAIN # Base for MQTT topics

# --- Renamed Keys ---
CONF_KEY_MIN_THRESHOLD = "min_vpd"
CONF_KEY_MAX_THRESHOLD = "max_vpd"
CONF_KEY_INITIAL_MIN_THRESHOLD = "initial_min_vpd" # For config flow default
CONF_KEY_INITIAL_MAX_THRESHOLD = "initial_max_vpd" # For config flow default
# --- Key for Toggle ---
CONF_KEY_CREATE_THRESHOLDS = "create_threshold_entities"
# --- Default Values ---
DEFAULT_MIN_THRESHOLD = 0.85
DEFAULT_MAX_THRESHOLD = 1.15
DEFAULT_THRESHOLD_MIN_LIMIT = 0.1 # Renamed for clarity (limit for the number entity)
DEFAULT_THRESHOLD_MAX_LIMIT = 2.5 # Renamed for clarity (limit for the number entity)
DEFAULT_THRESHOLD_STEP = 0.01