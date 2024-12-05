"""Light platform for BESTIN"""

from __future__ import annotations

from typing import Optional

from homeassistant.components.light import (
    ColorMode,
    DOMAIN as LIGHT_DOMAIN,
    LightEntity,
)

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .device import BestinDevice
from .hub import BestinHub
from .const import NEW_LIGHT


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """Setup light platform."""
    hub: BestinHub = BestinHub.get_hub(hass, entry)
    hub.entity_groups[LIGHT_DOMAIN] = set()

    @callback
    def async_add_light(devices=None):
        if devices is None:
            devices = hub.api.get_devices_from_domain(LIGHT_DOMAIN)

        entities = [
            BestinLight(device, hub) 
            for device in devices 
            if device.unique_id not in hub.entity_groups[LIGHT_DOMAIN]
        ]
        
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, hub.async_signal_new_device(NEW_LIGHT), async_add_light
        )
    )
    async_add_light()


class BestinLight(BestinDevice, LightEntity):
    """Define the Light."""
    TYPE = LIGHT_DOMAIN

    def __init__(self, device, hub):
        """Initialize the light."""
        super().__init__(device, hub)
        self._color_mode = ColorMode.ONOFF
        self._supported_color_modes = {ColorMode.ONOFF}
        
    @property
    def color_mode(self) -> ColorMode:
        """Return the color mode of the light."""
        return self._color_mode
    
    @property
    def supported_color_modes(self) -> set[ColorMode]:
        """Return the list of supported color modes."""
        return self._supported_color_modes
    
    @property
    def is_on(self) -> bool:
        """Return true if switch is on."""
        return self._dev_info.device_state

    @property
    def brightness(self) -> Optional[int]:
        """Return the current brightness."""
        return None
    
    @property
    def color_temp_kelvin(self) -> Optional[int]:
        """The current color temperature in Kelvin."""
        return None

    @property
    def max_color_temp_kelvin(self) -> int:
        """The highest supported color temperature in Kelvin."""
        return None

    @property
    def min_color_temp_kelvin(self) -> int:
        """The lowest supported color temperature in Kelvin."""
        return None

    async def async_turn_on(self, **kwargs):
        """Turn on light."""
        self.set_command(True)

    async def async_turn_off(self, **kwargs):
        """Turn off light."""
        self.set_command(False)
