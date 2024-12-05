"""Base class for BESTIN devices."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_UNIQUE_ID
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity, DeviceInfo

from .util import remove_colon
from .const import DOMAIN, MAIN_DEVICES, DEVICE_TYPE, ROOM_ID


class BestinBase:
    """Base class for BESTIN devices."""

    def __init__(self, device, hub):
        """Initialize device and hub."""
        self._device = device
        self._dev_info = device.dev_info
        self.hub = hub
    
    def set_command(self, data: Any = None, **kwargs):
        """Send command to device."""
        self._device.set_command(self._device, data, **kwargs)
    
    @property
    def unique_id(self) -> str:
        """Get unique device ID."""
        return self._device.unique_id
    
    @property
    def device_info(self) -> DeviceInfo:
        """Get device registry information."""
        if self._dev_info.device_type not in MAIN_DEVICES:
            device_type = remove_colon(self._dev_info.device_type)
            device_name = f"{self.hub.name} {device_type}"
        else:
            device_type = self.hub.model
            device_name = self.hub.name

        return DeviceInfo(
            connections={(self.hub.host, self.unique_id)},
            identifiers={(DOMAIN, f"{self.hub.name}_{device_type}_{self.hub.host}")},
            manufacturer="HDC Labs Co., Ltd.",
            model=self.hub.name,
            name=device_name,
            sw_version=self.hub.sw_version,
            via_device=(DOMAIN, self.hub.host),
        )


class BestinDevice(BestinBase, Entity):
    """Define the Bestin Device entity."""

    TYPE = ""

    def __init__(self, device, hub):
        """Initialize device and update callbacks."""
        super().__init__(device, hub)
        self.hub.entity_groups[self.TYPE].add(self.unique_id)
        self._attr_has_entity_name = True
        self._attr_name = self._dev_info.device_name

    @property
    def entity_registry_enabled_default(self):
        """Check if the entity is enabled by default."""
        return True

    async def async_added_to_hass(self):
        """Subscribe to device events upon addition to HASS."""
        self._device.add_callback(self.async_update_callback)
        self.hub.entity_to_id[self.entity_id] = self._dev_info.device_id
        self.schedule_update_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Cleanup when the entity is removed from HASS."""
        self._device.remove_callback(self.async_update_callback)
        del self.hub.entity_to_id[self.entity_id]
        self.hub.entity_groups[self.TYPE].remove(self.unique_id)

    @callback
    def async_restore_last_state(self, last_state) -> None:
        """Restore the last known state (not implemented)."""
        pass

    @callback
    def async_update_callback(self):
        """Trigger an update of the device state."""
        self.async_schedule_update_ha_state()

    @property
    def available(self) -> bool:
        """Check if the device is available."""
        return self.hub.available

    @property
    def should_poll(self) -> bool:
        """Determine if the device requires polling."""
        return False

    @property
    def extra_state_attributes(self) -> dict:
        """Get additional state attributes."""
        attributes = {
            CONF_UNIQUE_ID: self.unique_id,
            ROOM_ID: self._dev_info.room_id,
            DEVICE_TYPE: self._dev_info.device_type,
        }
        return attributes
