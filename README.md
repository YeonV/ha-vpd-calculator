# Home Assistant VPD Calculator

[![creator](https://img.shields.io/badge/CREATOR-Yeon-blue.svg?logo=github&logoColor=white)](https://github.com/YeonV) [![creator](https://img.shields.io/badge/A.K.A-Blade-darkred.svg?logo=github&logoColor=white)](https://github.com/YeonV)
<!-- Add other badges like version, HACS support later -->


Calculate Vapor Pressure Deficit (VPD) directly within Home Assistant and link the resulting sensor to an existing device!

This custom integration provides a simple way to create VPD sensors based on existing temperature and humidity sensors in your Home Assistant setup. Unlike standard template sensors defined in YAML, sensors created by this integration can be directly associated with a specific device (like your grow tent controller, weather station, etc.) via the configuration UI, making them appear neatly on that device's page.

## Features

*   Calculates VPD using standard formulas.
*   Uses existing Home Assistant temperature and humidity sensor entities as inputs.
*   Allows configuration of a leaf temperature offset (delta between air and leaf temperature).
*   **Crucially:** Links the created VPD sensor to a user-selected target device via the UI Config Flow.
*   Configurable via the Home Assistant UI (no YAML editing required for setup).
*   Supports multiple instances for different sensor pairs or devices.

## Prerequisites

*   Home Assistant instance.
*   Existing temperature and humidity sensor entities within Home Assistant that report air temperature (°C or °F) and relative humidity (%).
*   Access to the Home Assistant configuration directory if installing manually.

## Installation

### Manual Installation (Recommended for now)

1.  Ensure you have access to your Home Assistant configuration directory (e.g., via Samba, SSH, or File Editor addon).
2.  Download the latest release or clone this repository.
3.  Locate the `vpd_calculator` folder within the downloaded/cloned files. This folder contains files like `manifest.json`, `__init__.py`, etc.
4.  Copy the **entire `vpd_calculator` folder** into the `custom_components` directory within your Home Assistant configuration directory. If `custom_components` doesn't exist, create it.
    *   Your final structure should look like: `<config_dir>/custom_components/vpd_calculator/manifest.json`
5.  **Restart Home Assistant.** This is crucial for Home Assistant to detect the new integration.

### HACS Installation (Not Yet Available)

This integration is not yet submitted to the default HACS repository. Once it is, the recommended installation method will be via HACS:

1.  Ensure HACS is installed and configured.
2.  *(Once available)* Navigate to HACS -> Integrations.
3.  *(Once available)* Search for "VPD Calculator" and install it.
4.  Restart Home Assistant.

*(Alternatively, you can add this GitHub repository as a [Custom Repository](https://hacs.xyz/docs/faq/custom_repositories/) in HACS under the "Integration" category and then install from there.)*

## Configuration

Once installed and Home Assistant has restarted, you can add and configure VPD sensors:

1.  Navigate to **Settings** -> **Devices & Services**.
2.  Click the **+ Add Integration** button in the bottom right.
3.  Search for "**VPD Calculator**" and select it.
4.  A configuration dialog will appear. Fill in the following fields:
    *   **Name:** A unique, user-friendly name for this specific VPD sensor instance (e.g., "Grow Tent VPD", "Living Room VPD"). This will be used for the entity name.
    *   **Temperature Sensor:** Select the existing temperature sensor entity that provides the air temperature.
    *   **Humidity Sensor:** Select the existing humidity sensor entity that provides the relative air humidity.
    *   **Leaf Temperature Offset:** Enter the estimated difference between the leaf surface temperature and the air temperature. Use positive values if leaves are warmer (e.g., under intense light), negative if cooler (e.g., high transpiration), or 0.0 if unknown or assuming they are the same. The unit should match your temperature sensor's unit. Default is usually 0.0.
    *   **Target Device:** **This is key for linking!** Select the existing device you want this VPD sensor associated with from the dropdown list (e.g., select your "Smart Growing" device). The new VPD sensor will appear on this device's page.
5.  Click **Submit**.

The integration will create a new sensor entity (e.g., `sensor.grow_tent_vpd` based on the name you provided).

You can repeat steps 2-5 to create multiple VPD sensors for different areas or using different source sensors/devices.

## Usage

The created VPD sensor behaves like any other sensor in Home Assistant:

*   It will appear on the device page of the "Target Device" you selected during configuration.
*   You can add it to your dashboards (Lovelace UI).
*   You can use its state in automations (e.g., trigger ventilation or humidification based on VPD thresholds).
*   Its unit of measurement is Kilopascals (kPa).

## Contributing

Contributions are welcome! If you find issues or have suggestions for improvements, please open an issue or submit a pull request on the [GitHub repository](https://github.com/YeonV/ha-vpd-calculator).

## License

This project is licensed under the [MIT](LICENSE). *(You should add a LICENSE file to your repository - Apache 2.0 or MIT are common choices)*.
