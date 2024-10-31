"""Sensor platform for BESTIN"""

from __future__ import annotations

from homeassistant.components.sensor import (
    DOMAIN as DOMAIN_SENSOR,
    SensorDeviceClass
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    UnitOfVolume,
    UnitOfVolumeFlowRate
)
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import NEW_SENSOR
from .device import BestinDevice
from .hub import BestinHub

DEVICE_ICON = {
    "light:dcvalue": "mdi:flash",
    "outlet:powercons": "mdi:flash",
    "electric:realtime": "mdi:flash",
    "electric:total": "mdi:lightning-bolt",
    "gas:realtime": "mdi:gas-cylinder",
    "gas:total": "mdi:gas-cylinder",
    "heat:realtime": "mdi:radiator",
    "heat:total": "mdi:thermometer-lines",
    "hotwater:realtime": "mdi:water-boiler",
    "hotwater:total": "mdi:water-boiler",
    "water:realtime": "mdi:water-pump",
    "water:total": "mdi:water-pump"
}

DEVICE_CLASS = {
    "light:dcvalue": UnitOfPower.WATT,
    "outlet:cutvalue": UnitOfPower.WATT,
    "outlet:powercons": UnitOfPower.WATT,
    "electric:realtime": SensorDeviceClass.POWER,
    "electric:total": SensorDeviceClass.ENERGY,
    "gas:total": SensorDeviceClass.GAS,
    "water:total": SensorDeviceClass.WATER,
}

DEVICE_UNIT = {
    "light:dcvalue": UnitOfPower.WATT,
    "outlet:cutvalue": UnitOfPower.WATT,
    "outlet:powercons": UnitOfPower.WATT,
    "electric:realtime": UnitOfPower.WATT,
    "electric:total": UnitOfEnergy.KILO_WATT_HOUR,
    "gas:realtime": UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    "gas:total": UnitOfVolume.CUBIC_METERS,
    "heat:realtime": UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    "heat:total": UnitOfVolume.CUBIC_METERS,
    "hotwater:realtime": UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    "hotwater:total": UnitOfVolume.CUBIC_METERS,
    "water:realtime": UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    "water:total": UnitOfVolume.CUBIC_METERS,
}

VALUE_CONVERSION = {
    "electric:total": lambda value: round(value / 100, 2),
    "electric:realtime": lambda value: value,
    "gas:total": lambda value: round(value / 1000, 2),
    "gas:realtime": lambda value: value / 10,
    "heat:total": lambda value: round(value / 1000, 2),
    "heat:realtime": [
        lambda value: value,
        lambda value: value / 1000
    ],
    "hotwater:total": lambda value: round(value / 1000, 2),
    "hotwater:realtime": [
        lambda value: value,
        lambda value: value / 1000
    ],
    "water:total": lambda value: round(value / 1000, 2),
    "water:realtime": [
        lambda value: value,
        lambda value: value / 1000,
    ],
}


def extract_and_transform(identifier: str) -> str:
    if "energy_" in identifier:
        extracted_segment = identifier.split("energy_")[1]
    else:
        extracted_segment = ':'.join([identifier.split("_")[1], identifier.split("_")[3]])

    transformed_segment = extracted_segment.replace("_", ":")
    return transformed_segment


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """Setup sensor platform."""
    hub: BestinHub = BestinHub.get_hub(hass, entry)
    hub.entity_groups[DOMAIN_SENSOR] = set()

    @callback
    def async_add_sensor(devices=None):
        if devices is None:
            devices = hub.api.get_devices_from_domain(DOMAIN_SENSOR)

        entities = [
            BestinSensor(device, hub) 
            for device in devices 
            if device.unique_id not in hub.entity_groups[DOMAIN_SENSOR]
        ]

        if entities:
            async_add_entities(entities)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, hub.async_signal_new_device(NEW_SENSOR), async_add_sensor
        )
    )
    async_add_sensor()


class BestinSensor(BestinDevice):
    """Defined the Sensor."""
    TYPE = DOMAIN_SENSOR

    def __init__(self, device, hub) -> None:
        """Initialize the sensor."""
        super().__init__(device, hub)
        self._attr_id = extract_and_transform(self._device_info.device_id)
        self._attr_icon = DEVICE_ICON.get(self._attr_id, None)

    @property
    def state(self):
        """Return the state of the sensor."""
        if self._attr_id in VALUE_CONVERSION:
            factor = VALUE_CONVERSION[self._attr_id]

            if isinstance(factor, list) and len(factor) == 2:
                factor = factor[0] if self.hub.wp_version == "General" else factor[1]
            return factor(self._device_info.state)
        else:
            return self._device_info.state
    
    @property
    def device_class(self):
        """Return the class of the sensor."""
        return DEVICE_CLASS.get(self._attr_id, None)

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this sensor."""
        return DEVICE_UNIT.get(self._attr_id, None)

    @property
    def state_class(self):
        """Type of this sensor state."""
        return (
            "total_increasing" if "total" in self._attr_id else "measurement"
        )
