"""Base class for BESTIN devices."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.entity import Entity, DeviceInfo
from homeassistant.core import callback

from .const import DOMAIN, MAIN_DEVICES
from .until import formatted_name


class BestinBase:
    """Base class for BESTIN devices."""

    def __init__(self, device, hub):
        """Set up device and update callbacks."""
        self._device = device
        self._device_info = device.info
        self.hub = hub
    
    async def enqueue_command(self, data: Any = None, **kwargs):
        """Send commands to the device."""
        await self._device.enqueue_command(
            self._device_info.device_id, data, **kwargs
        )

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._device.unique_id

    @property
    def device_info(self) -> DeviceInfo:
        """Return device registry information for this entity."""
        device_info = {
            "connections": {(self.hub.hub_id, self.unique_id)},
            "identifiers": {(DOMAIN, f"{self.hub.wp_version}_{self.hub.model}")},
            "manufacturer": "HDC Labs Co., Ltd.",
            "model": self.hub.wp_version,
            "name": self.hub.name,
            "sw_version": self.hub.sw_version,
            "via_device": (DOMAIN, self.hub.hub_id),
        }
        if (device_type := self._device_info.device_type) not in MAIN_DEVICES:
            formatted_device_type = formatted_name(device_type)
            device_info["identifiers"] = {
                (DOMAIN, f"{self.hub.wp_version}_{formatted_device_type}")
            }
            device_info["name"] = f"{self.hub.name} {formatted_device_type}"
        
        return DeviceInfo(**device_info)


class BestinDevice(BestinBase, Entity):
    """Define the Bestin Device entity."""

    TYPE = ""

    def __init__(self, device, hub):
        """Set up device and update callbacks."""
        super().__init__(device, hub)
        self.hub.entity_groups[self.TYPE].add(self.unique_id)
        self._attr_name = self._device_info.name
        self._attr_has_entity_name = True

    @property
    def entity_registry_enabled_default(self):
        """Return if the entity should be enabled when first added to the entity registry."""
        return True

    async def async_added_to_hass(self):
        """Subscribe to device events."""
        self._device.add_callback(self.async_update_callback)
        self.hub.entity_to_id[self.entity_id] = self._device_info.device_id
        self.schedule_update_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Disconnect device object when removed."""
        self._device.remove_callback(self.async_update_callback)
        del self.hub.entity_to_id[self.entity_id]
        self.hub.entity_groups[self.TYPE].remove(self.unique_id)

    @callback
    def async_restore_last_state(self, last_state) -> None:
        """Restore previous state."""
        pass

    @callback
    def async_update_callback(self):
        """Update the device's state."""
        self.async_schedule_update_ha_state()

    @property
    def available(self) -> bool:
        """Return True if device is available."""
        return self.hub.available

    @property
    def should_poll(self) -> bool:
        """Determine if the device should be polled."""
        return self.hub.is_polling

    @property
    def extra_state_attributes(self) -> dict:
        """Return the state attributes of the sensor."""
        attributes = {
            "unique_id": self.unique_id,
            "device_type": self._device_info.device_type,
            "device_room": self._device_info.room,
        }
        if self.should_poll and not attributes["device_type"].startswith("elevator"):
            attributes["last_update_time"] = self.hub.api.last_update_time
        
        return attributes
