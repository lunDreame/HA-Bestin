"""Climate platform for BESTIN"""

from __future__ import annotations

from homeassistant.components.climate import DOMAIN as CLIMATE_DOMAIN, ClimateEntity
from homeassistant.components.climate.const import (
    ATTR_CURRENT_TEMPERATURE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
    HVACMode,
)

from homeassistant.const import ATTR_STATE, ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry

from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .device import BestinDevice
from .hub import BestinHub
from .const import NEW_CLIMATE


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> bool:
    """Setup climate platform."""
    hub: BestinHub = BestinHub.get_hub(hass, entry)
    hub.entity_groups[CLIMATE_DOMAIN] = set()

    @callback
    def async_add_climate(devices=None):
        if devices is None:
            devices = hub.api.get_devices_from_domain(CLIMATE_DOMAIN)

        entities = [
            BestinClimate(device, hub) 
            for device in devices 
            if device.unique_id not in hub.entity_groups[CLIMATE_DOMAIN]
        ]

        if entities:
            async_add_entities(entities)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, hub.async_signal_new_device(NEW_CLIMATE), async_add_climate
        )
    )
    async_add_climate()


class BestinClimate(BestinDevice, ClimateEntity):
    """Defined the Climate."""
    TYPE = CLIMATE_DOMAIN
    
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, device, hub: BestinHub):
        """Initialize the climate."""
        super().__init__(device, hub)
        self._supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE | 
            ClimateEntityFeature.TURN_ON | 
            ClimateEntityFeature.TURN_OFF
        )
        self._hvac_modes = [HVACMode.OFF, HVACMode.HEAT]

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the list of supported features."""
        return self._supported_features

    @property
    def hvac_mode(self) -> HVACMode:
        """Return hvac operation ie. heat, cool mode.

        Need to be one of HVAC_MODE_*.
        """
        return HVACMode.HEAT if self._dev_info.device_state[ATTR_STATE] else HVACMode.OFF

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Return the list of available hvac operation modes."""
        return self._hvac_modes

    async def async_turn_on(self) -> None:
        """Turn the entity on."""

    async def async_turn_off(self) -> None:
        """Turn the entity off."""

    async def async_set_hvac_mode(self, hvac_mode: str) -> None:
        """Set new target hvac mode."""
        if hvac_mode not in self.hvac_modes:
            raise ValueError(f"Unsupported HVAC mode {hvac_mode}")
        
        self.set_command(hvac_mode=hvac_mode==HVACMode.HEAT)

    @property
    def preset_mode(self):
        """Return the current preset mode, e.g., home, away, temp.
        Requires ClimateEntityFeature.PRESET_MODE.
        """

    @property
    def preset_modes(self) -> list:
        """Return the list of available preset modes."""

    async def async_set_preset_mode(self, preset_mode):
        """Set new target preset mode."""

    @property
    def hvac_action(self):
        """Return the current action."""

    @property
    def current_temperature(self) -> float:
        """Return the current temperature."""
        return self._dev_info.device_state[ATTR_CURRENT_TEMPERATURE]

    @property
    def target_temperature(self) -> float:
        """Return the target temperature."""
        return self._dev_info.device_state[SERVICE_SET_TEMPERATURE]

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            raise ValueError(f"Expected attribute {ATTR_TEMPERATURE}")
        
        self.set_command(set_temperature=float(kwargs[ATTR_TEMPERATURE]))

    @property
    def temperature_unit(self) -> UnitOfTemperature:
        """Return the unit of measurement."""
        return UnitOfTemperature.CELSIUS

    @property
    def max_temp(self) -> int:
        """Max tempreature."""
        return 40

    @property
    def min_temp(self) -> int:
        """Min tempreature."""
        return 5

    @property
    def target_temperature_step(self) -> float:
        """Step tempreature."""
        return 0.5
