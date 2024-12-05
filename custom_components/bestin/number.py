"""Number platform for BESTIN"""

from __future__ import annotations

from homeassistant.components.number import (
    DOMAIN as DOMAIN_NUMBER,
    ATTR_MIN,
    ATTR_MAX,
    ATTR_STEP,
    NumberEntity,
)

from homeassistant.const import (
    ATTR_STATE,
    UnitOfTemperature,
    UnitOfTime
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .device import BestinDevice
from .hub import BestinHub
from .const import NEW_NUMBER


DEVICE_ICON = {
    "fan:timer": "mdi:fan-clock",
    "heat:set": "mdi:radiator",
    "hotwater:set": "mdi:water-boiler",
}

DEVICE_UNIT = {
    "fan:timer": UnitOfTime.MINUTES,
    "heat:set": UnitOfTemperature.CELSIUS,
    "hotwater:set": UnitOfTemperature.CELSIUS,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """Setup number platform."""
    hub: BestinHub = BestinHub.get_hub(hass, entry)
    hub.entity_groups[DOMAIN_NUMBER] = set()

    @callback
    def async_add_number(devices=None):
        if devices is None:
            devices = hub.api.get_devices_from_domain(DOMAIN_NUMBER)

        entities = [
            BestinNumber(device, hub) 
            for device in devices 
            if device.unique_id not in hub.entity_groups[DOMAIN_NUMBER]
        ]

        if entities:
            async_add_entities(entities)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, hub.async_signal_new_device(NEW_NUMBER), async_add_number
        )
    )
    async_add_number()


class BestinNumber(BestinDevice, NumberEntity):
    """Defined the Number."""
    TYPE = DOMAIN_NUMBER

    def __init__(self, device, hub) -> None:
        """Initialize the number."""
        super().__init__(device, hub)
        self._attr_icon = DEVICE_ICON.get(self._dev_info.device_type)
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        device_state = self._dev_info.device_state
        if isinstance(device_state, dict):
            return device_state[ATTR_STATE]
        return device_state
    
    @property
    def native_min_value(self):
        """Return the minimum value."""
        return self._dev_info.device_state[ATTR_MIN]
    
    @property
    def native_max_value(self):
        """Return the maximum value."""
        return self._dev_info.device_state[ATTR_MAX]
    
    @property
    def native_step(self):
        """Return the increment/decrement step."""
        return self._dev_info.device_state[ATTR_STEP]
    
    @property
    def native_unit_of_measurement(self):
        """Return the unit of measurement of this sensor."""
        return DEVICE_UNIT.get(self._dev_info.device_type)
    
    async def async_set_native_value(self, value: float) -> None:
        """Update the current value."""
        self.set_command(value)
        