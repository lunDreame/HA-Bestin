import logging

from typing import Callable, Any, Set
from dataclasses import dataclass, field

from homeassistant.const import Platform

LOGGER = logging.getLogger(__package__)

DOMAIN = "bestin"
NAME = "BESTIN"
VERSION = "1.2.0"

PLATFORMS: list[Platform] = [
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.FAN,
    Platform.LIGHT,
    Platform.SENSOR,
    Platform.SWITCH,
]

DEFAULT_PORT = 8899

EC_TYPE = "ec_type"

SEND_RETRY = "send_retry"
DEVICE_TYPE = "device_type"
SUB_TYPE = "sub_type"
ROOM_ID = "room_id"
SUB_ID = "sub_id"
VALUE = "value"
SEQ_NUMBER = "seq_number"

SPEED_LOW = 1
SPEED_MEDIUM = 2
SPEED_HIGH = 3

PRESET_NONE = "None"
PRESET_NV = "Natural"

BRAND_PREFIX = "bestin"

NEW_CLIMATE = "climates"
NEW_NUMBER = "numbers"
NEW_FAN = "fans"
NEW_LIGHT = "lights"
NEW_SENSOR = "sensors"
NEW_SWITCH = "switchs"

MAIN_DEVICES: list[str] = [
    "fan",
    "fan:timer",
    "gas",
    "doorlock"
]

PLATFORM_SIGNAL_MAP = {
    Platform.CLIMATE.value: NEW_CLIMATE,
    Platform.NUMBER.value: NEW_NUMBER,
    Platform.FAN.value: NEW_FAN,
    Platform.LIGHT.value: NEW_LIGHT,
    Platform.SENSOR.value: NEW_SENSOR,
    Platform.SWITCH.value: NEW_SWITCH,
}

DEVICE_PLATFORM_MAP = {
    "thermostat": Platform.CLIMATE.value,
    "heatwater:set": Platform.NUMBER.value,
    "hotwater:set": Platform.NUMBER.value,
    "fan": Platform.FAN.value,
    "fan:timer": Platform.NUMBER.value,
    "light": Platform.LIGHT.value,
    "dimming": Platform.LIGHT.value,
    "light:powerusage": Platform.SENSOR.value,
    "energy:totalusage": Platform.SENSOR.value,
    "energy:realtimeusage": Platform.SENSOR.value,
    "gas": Platform.SWITCH.value,
    "doorlock": Platform.SWITCH.value,
    "outlet": Platform.SWITCH.value,
    "outlet:cutoffvalue": Platform.SENSOR.value,
    "outlet:powerusage": Platform.SENSOR.value,
    "outlet:standbycutoff": Platform.SWITCH.value,
}

@dataclass
class DeviceInfo:
    """Represents device information."""
    device_id: str
    device_name: str
    device_type: str
    sub_type: str | None
    room_id: str
    sub_id: str | None
    device_state: Any

@dataclass
class Device:
    """Represents a device."""
    set_command: Callable[..., None]
    domain: str
    unique_id: str
    dev_info: DeviceInfo
    callbacks: Set[Callable[..., None]] = field(default_factory=set)

    def add_callback(self, callback: Callable[..., None]) -> None:
        """Adds a callback to the set of callbacks."""
        self.callbacks.add(callback)

    def remove_callback(self, callback: Callable[..., None]) -> None:
        """Removes a callback from the set of callbacks."""
        self.callbacks.discard(callback)
    
    def update_callback(self) -> None:
        """Calls all callbacks."""
        for callback in self.callbacks:
            assert callable(callback), "Callback should be callable"
            callback()
