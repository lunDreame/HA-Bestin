"""Command handler for Bestin devices."""

from __future__ import annotations

from typing import Any
from homeassistant.components.light import COLOR_MODE_BRIGHTNESS
from homeassistant.components.climate.const import SERVICE_SET_TEMPERATURE
from homeassistant.components.fan import SERVICE_SET_PERCENTAGE, ATTR_PRESET_MODE

from .packet_handler import EcType
from .const import LOGGER


class CommandPacket:
    """Command packet for Bestin devices."""

    EC_ROOM_MAP: dict[EcType, int] = {
        EcType.EC3: 0x30,
        EcType.EC5: 0x50,
    }

    def __init__(
        self,
        cls,
        device_type: str,
        sub_type: str | None,
        room_id: str,
        sub_id: str | None,
        value: Any,
        seq_number: int,
    ) -> None:
        """Initialize the CommandPacket."""
        self.cls = cls
        self.device_type = device_type
        self.sub_type = sub_type
        self.room_id = int(room_id)
        self.sub_id = self._extract_sub_id(sub_id)
        self.value = value
        self.seq_number = seq_number

    def create_packet(self) -> bytearray:
        """Unified packet creation handler based on device type."""
        packet_methods = {
            "light": self._create_light_packet,
            "dimming": self._create_light_packet,
            "outlet": self._create_outlet_packet,
            "thermostat": self._create_thermostat_packet,
            "gas": self._create_fixed_packet,       # Fixed structure
            "doorlock": self._create_fixed_packet,  # Fixed structure
            "fan": self._create_fan_packet,
        }
        create_method = packet_methods.get(self.device_type)
        if not create_method:
            LOGGER.warning(f"No packet generation method for device type: {self.device_type}.")
            return None
        try:
            return create_method()
        except Exception as ex:
            LOGGER.error(f"Failed to generate packet for device type {self.device_type}: {ex}")
            return None
        
    @staticmethod
    def _extract_sub_id(sub_id: str | None) -> int:
        """Extract specific characters from the Sub ID."""
        if not sub_id:
            return 0
        sub_parts = sub_id.split(" ")
        return int(sub_parts[-1]) if len(sub_parts) > 2 else 0

    def _get_common_header(self, header: int) -> int:
        """Get the common header value."""
        return header + self.EC_ROOM_MAP.get(self.cls.get_ec_type(), 0)

    def _create_common_packet(
        self, header: int, length: int, packet_type: int
    ) -> bytearray:
        """Create a common packet structure."""
        packet = bytearray([
            0x02,
            self._get_common_header(header),
            length,
            packet_type,
            self.seq_number & 0xFF,
        ])
        packet.extend([0x00] * (length - len(packet)))
        return packet

    def _fill_packet(self, packet: bytearray, indices: list[int], values: list[int]) -> None:
        """Fill specific indices in the packet with given values."""
        for index, value in zip(indices, values):
            packet[index] = value

    def _create_light_packet(self) -> bytearray:
        """Generate a packet for light control."""
        onoff = 0x01 if self.value else 0x00
        flag = 0x80 if self.value else 0x00

        if self.cls.get_ec_type() == EcType.EC3:
            self.sub_id += 1
            if not self.value:
                onoff = 0x02
            packet = self._create_common_packet(self.room_id, 0x0E, 0x21)
            self._fill_packet(packet, [5, 6, 7, 8, 9, 10, 11, 12], [0x01, 0x00, self.sub_id, onoff, 0xFF, 0xFF, 0x00, 0xFF])
            if isinstance(self.value, bool):
                return packet
            packet[9 if self.sub_type == COLOR_MODE_BRIGHTNESS else 10] = self.value
        elif self.cls.get_ec_type() == EcType.EC5:
            packet = self._create_common_packet(self.room_id, 0x0A, 0x12)
            self._fill_packet(packet, [5, 6], [onoff, 10 if self.sub_id == 4 else 1 << self.sub_id])
        else:
            packet = self._create_common_packet(0x31, 0x0D, 0x01)
            self._fill_packet(packet, [5, 6, 11], [self.room_id & 0x0F, (1 << self.sub_id) | flag, onoff * 0x04])
        return packet

    def _create_outlet_packet(self) -> bytearray:
        """Generate a packet for outlet control."""
        onoff = 0x01 if self.value else 0x02
        flag = 0x80 if self.value else 0x00

        if self.cls.get_ec_type() == EcType.EC3:
            packet = self._create_common_packet(self.room_id, 0x09, 0x22)
            self._fill_packet(packet, [5, 6, 7], [0x01, (self.sub_id + 1) & 0x0F, onoff])
            if self.sub_type == "standbycutoff":
                packet[7] *= 0x10
        elif self.cls.get_ec_type() == EcType.EC5:
            packet = self._create_common_packet(self.room_id, 0x0C, 0x12)
            self._fill_packet(packet, [8, 9, 10], [0x01, (self.sub_id + 1) & 0x0F, onoff])
        else:
            packet = self._create_common_packet(0x31, 0x0D, 0x01)
            self._fill_packet(packet, [5, 7], [self.room_id & 0x0F, (1 << self.sub_id) | flag])
            if self.sub_type == "standbycutoff":
                packet[8] += 0x03
        return packet

    def _create_thermostat_packet(self) -> bytearray:
        """Generate a packet for thermostat control."""
        packet = self._create_common_packet(0x28, 0x0E, 0x12)
        packet[5] = self.room_id & 0x0F

        if self.sub_type == SERVICE_SET_TEMPERATURE:
            int_part = int(self.value)
            float_part = self.value - int_part
            packet[7] = int_part & 0xFF
            if float_part != 0:
                packet[7] |= 0x40
        else:
            packet[6] = 0x01 if self.value else 0x02

        return packet

    def _create_fixed_packet(self) -> bytearray:
        """Generate a fixed structure packet for gas and doorlock."""
        header_map = {"gas": 0x31, "doorlock": 0x41}
        header = header_map.get(self.device_type, 0x00)
        packet = self._create_common_packet(header, 0x02, self.seq_number)
        if self.device_type == "doorlock":
            packet[4] = 0x01
        return packet

    def _create_fan_packet(self) -> bytearray:
        """Generate a packet for fan control."""
        packet = self._create_common_packet(0x61, 0x00, self.seq_number)

        if self.sub_type == SERVICE_SET_PERCENTAGE:
            packet[2] = 0x03
            packet[6] = self.value
        elif self.sub_type == ATTR_PRESET_MODE:
            packet[2] = 0x07
            packet[5] = 0x10 if self.value else 0x00
        else:
            packet[2] = 0x01
            self._fill_packet(packet, [5, 6], [0x01 if self.value else 0x00, 0x01])

        return packet