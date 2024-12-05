"""Command handler for Bestin devices."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import COLOR_MODE_BRIGHTNESS
from homeassistant.components.climate.const import SERVICE_SET_TEMPERATURE
from homeassistant.components.fan import SERVICE_SET_PERCENTAGE, ATTR_PRESET_MODE

from .packet_handler import EcType
#from .controller import BestinController
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
        self.sub_id = self.extract_sub_id(sub_id)
        self.value = value
        self.seq_number = seq_number

    def create(self) -> bytearray | None:
        """Generate a command packet for the device."""
        device_packet = getattr(self, f"create_{self.device_type}_packet", None)
        if device_packet is None:
            LOGGER.warning(f"No packet generation method for {self.device_type} device.")
            return None
        try:
            return device_packet()
        except Exception as ex:
            LOGGER.error(f"Failed to generate packet for {self.device_type} device: {ex}")
            return None
        
    def extract_sub_id(self, sub_id: str | None) -> int:
        """Extracts specific characters from the Sub ID."""
        if sub_id is None:
            return 0
        sub_parts = sub_id.split(" ")
        return int(sub_parts[-1]) if len(sub_parts) > 2 else 0
    
    def create_common_packet(
        self, header: int, length: int, packet_type: int, seq_number: int
    ) -> bytearray:
        """Create a common packet with the given header, length, packet type, and sequence number."""
        if header not in {0x28, 0x31}:
            header += self.EC_ROOM_MAP.get(self.cls.get_ec_type())

        packet = bytearray([
            0x02,
            header & 0xFF,
            length & 0xFF,
            packet_type & 0xFF,
            seq_number & 0xFF
        ])
        packet.extend(bytearray([0] * (length - 5)))
        return packet
    
    def create_light_packet(self) -> bytearray:
        """Generate a packet for light control."""
        onoff = 0x01 if self.value else 0x00
        flag = 0x80 if self.value else 0x00

        if self.cls.get_ec_type() == EcType.EC3:
            self.sub_id += 1
            if onoff == 0x00: 
                onoff += 0x02
            
            packet = self.create_common_packet(self.room_id, 0x0E, 0x21, self.seq_number)
            packet[5:13] = [0x01, 0x00, self.sub_id, onoff, 0xFF, 0xFF, 0x00, 0xFF]
            if not isinstance(self.value, bool):
                packet[8] = 0xFF
                packet[9 if self.sub_type == COLOR_MODE_BRIGHTNESS else 10] = self.value
        elif self.cls.get_ec_type() == EcType.EC5:
            packet = self.create_common_packet(self.room_id, 0x0A, 0x12, self.seq_number)
            packet[5] = onoff
            packet[6] = 10 if self.sub_id == 4 else 1 << self.sub_id
        else:
            packet = self.create_common_packet(0x31, 0x0D, 0x01, self.seq_number)
            packet[5] = self.room_id & 0x0F
            packet[6] = (1 << self.sub_id) | flag
            packet[11] = onoff * 0x04

        return packet

    def create_outlet_packet(self) -> bytearray:
        """Generate a packet for outlet control."""
        onoff = 0x01 if self.value else 0x02
        flag = 0x80 if self.value else 0x00

        if self.cls.get_ec_type() == EcType.EC3:
            packet = self.create_common_packet(self.room_id, 0x09, 0x22, self.seq_number)
            packet[5] = 0x01
            packet[6] = (self.sub_id + 1) & 0x0F
            packet[7] = onoff
            if self.sub_type == "standbycutoff":
                packet[7] *= 0x10
        elif self.cls.get_ec_type() == EcType.EC5:
            packet = self.create_common_packet(self.room_id, 0x0C, 0x12, self.seq_number)
            packet[8] = 0x01
            packet[9] = (self.sub_id + 1) & 0x0F
            packet[10] = onoff >> (onoff + 3) if self.sub_type else onoff
        else:
            packet = self.create_common_packet(0x31, 0x0D, 0x01, self.seq_number)
            packet[5] = self.room_id & 0x0F

            if self.sub_type == "standbycutoff":
                packet[8] = flag + 0x03
            else:
                packet[7] = (0x01 << self.sub_id) | flag
                packet[11] = (0x09 << self.sub_id) if self.value else 0x00

        return packet
    
    def create_thermostat_packet(self) -> bytearray:
        """Generate a packet for thermostat control."""
        packet = self.create_common_packet(0x28, 14, 0x12, self.seq_number)
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
    
    def create_gas_packet(self) -> bytearray:
        """Generate a packet for gas control."""
        packet = bytearray(
            [0x02, 0x31, 0x02, self.seq_number & 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        )
        return packet
    
    def create_doorlock_packet(self) -> bytearray:
        """Generate a packet for doorlock control."""
        packet = bytearray(
            [0x02, 0x41, 0x02, self.seq_number & 0xFF, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00]
        )
        return packet

    def create_fan_packet(self) -> bytearray:
        """Generate a packet for fan control."""
        packet = bytearray(
            [0x02, 0x61, 0x00, self.seq_number & 0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
        )
        if self.sub_type == SERVICE_SET_PERCENTAGE:
            packet[2] = 0x03
            packet[6] = self.value
        elif self.sub_type == ATTR_PRESET_MODE:
            packet[2] = 0x07
            packet[5] = 0x10 if self.value else 0x00
        else:
            packet[2] = 0x01
            packet[5] = 0x01 if self.value else 0x00
            packet[6] = 0x01

        return packet
    