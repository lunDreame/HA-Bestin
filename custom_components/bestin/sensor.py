"""Sensor platform for BESTIN"""

from __future__ import annotations

from homeassistant.components.sensor import (
    DOMAIN as DOMAIN_SENSOR,
    SensorEntity,
    SensorDeviceClass
)

from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    UnitOfVolume,
    UnitOfVolumeFlowRate
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .device import BestinDevice
from .hub import BestinHub
from .const import NEW_SENSOR


DEVICE_ICON = {
    "light:powerusage": "mdi:flash",
    "outlet:powerusage": "mdi:flash",
    "outlet:cutoffvalue": "mdi:lightning-bolt",
    "electric:realtimeusage": "mdi:flash",
    "electric:totalusage": "mdi:lightning-bolt",
    "gas:realtimeusage": "mdi:gas-cylinder",
    "gas:totalusage": "mdi:gas-cylinder",
    "heat:realtimeusage": "mdi:radiator",
    "heat:totalusage": "mdi:thermometer-lines",
    "hotwater:realtimeusage": "mdi:water-boiler",
    "hotwater:totalusage": "mdi:water-boiler",
    "water:realtimeusage": "mdi:water-pump",
    "water:totalusage": "mdi:water-pump"
}

DEVICE_CLASS = {
    "light:powerusage": SensorDeviceClass.POWER,
    "outlet:powerusage": SensorDeviceClass.POWER,
    "outlet:cutoffvalue": SensorDeviceClass.POWER,
    "electric:realtimeusage": SensorDeviceClass.POWER,
    "electric:totalusage": SensorDeviceClass.ENERGY,
    "gas:totalusage": SensorDeviceClass.GAS,
    "water:totalusage": SensorDeviceClass.WATER,
}

DEVICE_UNIT = {
    "light:powerusage": UnitOfPower.WATT,
    "outlet:powerusage": UnitOfPower.WATT,
    "outlet:cutoffvalue": UnitOfPower.WATT,
    "electric:realtimeusage": UnitOfPower.WATT,
    "electric:totalusage": UnitOfEnergy.KILO_WATT_HOUR,
    "gas:realtimeusage": UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    "gas:totalusage": UnitOfVolume.CUBIC_METERS,
    "heat:realtimeusage": UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    "heat:totalusage": UnitOfVolume.CUBIC_METERS,
    "hotwater:realtimeusage": UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    "hotwater:totalusage": UnitOfVolume.CUBIC_METERS,
    "water:realtimeusage": UnitOfVolumeFlowRate.CUBIC_METERS_PER_HOUR,
    "water:totalusage": UnitOfVolume.CUBIC_METERS,
}


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


class BestinSensor(BestinDevice, SensorEntity):
    """Defined the Sensor."""
    TYPE = DOMAIN_SENSOR

    def __init__(self, device, hub) -> None:
        """Initialize the sensor."""
        super().__init__(device, hub)
        self._attr_icon = DEVICE_ICON.get(self.sensor_format_id)
    
    @property
    def sensor_format_id(self):
        """Return the sensor format id."""
        if self._dev_info.device_type.startswith("energy"):
            return self._dev_info.device_type.replace("energy", self._dev_info.room_id)
        return self._dev_info.device_type
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self._dev_info.device_state
    
    @property
    def device_class(self):
        """Return the class of the sensor."""
        return DEVICE_CLASS.get(self.sensor_format_id)

    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement of this sensor."""
        return DEVICE_UNIT.get(self.sensor_format_id)

    @property
    def state_class(self):
        """Type of this sensor state."""
        if "usage" in self._dev_info.device_type:
            return "total_increasing" if "total" in self._dev_info.device_type else "measurement"
        return None
