"""Packet handler for Bestin devices."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from homeassistant.const import ATTR_STATE, WIND_SPEED
from homeassistant.components.climate.const import SERVICE_SET_TEMPERATURE, ATTR_CURRENT_TEMPERATURE
from homeassistant.components.number import ATTR_MIN, ATTR_MAX, ATTR_STEP

#from .controller import BestinController
from .const import LOGGER, EC_TYPE


class DeviceType(Enum):
    """Enum for device types."""
    DIMMING = "dimming"
    DOORLOCK = "doorlock"
    EC = "ec"
    ELEVATOR = "elevator"
    ENERGY = "energy"
    FAN = "fan"
    GAS = "gas"
    IAQ = "iaq"
    IGNORE = "ignore"
    LIGHT = "light"
    OUTLET = "outlet"
    THERMOSTAT = "thermostat"

class PacketType(Enum):
    """Enum for packet types."""
    QUERY = "query"
    RESPONSE = "response"
    PROMPT = "prompt"

class EcType(Enum):
    """Enum for ec types."""
    EC3 = "3"
    EC5 = "5"
    ECE = "e"

class EnergyType(Enum):
    """Enum for energy types."""
    ELECTRIC = 0x1
    WATER = 0x2
    HOTWATER = 0x3
    GAS = 0x4
    HEAT = 0x5

class EnergyMetric(Enum):
    """Enum for energy metrics."""
    TOTAL = "total"
    REALTIME = "realtime"

ENERGY_TO_VALUE = {
    (EnergyType.ELECTRIC, EnergyMetric.TOTAL): lambda val, _: round(val / 100, 2),
    (EnergyType.GAS, EnergyMetric.TOTAL): lambda val, _: round(val / 1000, 2),
    (EnergyType.GAS, EnergyMetric.REALTIME): lambda val, _: val / 10,
    (EnergyType.HEAT, EnergyMetric.TOTAL): lambda val, _: round(val / 1000, 2),
    (EnergyType.HEAT, EnergyMetric.REALTIME): lambda val, inc: val if inc == 8 else val / 1000,
    (EnergyType.HOTWATER, EnergyMetric.TOTAL): lambda val, _: round(val / 1000, 2),
    (EnergyType.HOTWATER, EnergyMetric.REALTIME): lambda val, inc: val if inc == 8 else val / 1000,
    (EnergyType.WATER, EnergyMetric.TOTAL): lambda val, _: round(val / 1000, 2),
    (EnergyType.WATER, EnergyMetric.REALTIME): lambda val, inc: val if inc == 8 else val / 1000,
}


class BasePacket:
    """Base class for packets."""

    @dataclass
    class Packet:
        """Class to represent a packet."""
        device_type: DeviceType
        packet_type: PacketType
        seq_number: int
        data: bytes

        def __str__(self) -> str:
            return f"Packet(device_type={self.device_type}, packet_type={self.packet_type}, seq_number={self.seq_number}, data={self.data})"

    HEADER_BYTES: dict[int, DeviceType | tuple[DeviceType, DeviceType | None]] = {
        0x28: DeviceType.THERMOSTAT,
        0x31: (DeviceType.GAS, DeviceType.EC),
        0x32: (DeviceType.IGNORE, DeviceType.EC),
        0x41: (DeviceType.DOORLOCK, DeviceType.IGNORE),
        0x42: DeviceType.IGNORE,
        0x61: DeviceType.FAN,
        0xB1: DeviceType.IAQ,
        0xC1: DeviceType.ELEVATOR,
        0xD1: DeviceType.ENERGY,
    }

    def __init__(self, packet: bytes) -> None:
        """Initialize the packet."""
        self.packet = packet
        self.current_position = 0

    def find_next_packet_start(self) -> int | None:
        """Find the next packet start."""
        try:
            return self.packet.index(0x02, self.current_position)
        except ValueError:
            return None

    def get_packet_length(self, start_idx: int, device_type) -> int:
        """Determine packet length based on device type and packet data."""
        length = self.packet[start_idx + 2]
        
        if device_type in {DeviceType.GAS, DeviceType.IGNORE} and length in {0x00, 0x80, 0x02, 0x82}:
            return 10
        if device_type == DeviceType.FAN:
            return 10

        return length

    def is_ec_condition(self, header_byte: int) -> bool:
        """Check if the header byte matches EC conditions."""
        upper_4bits = (header_byte >> 4) & 0xF
        lower_4bits = header_byte & 0xF
        return 1 <= upper_4bits <= 9 and (1 <= lower_4bits <= 6 or lower_4bits == 0xF)

    def get_device_type(self, header_byte: int, start_idx: int) -> DeviceType | None:
        """Determine device type based on header byte and packet type."""
        device_type = self.HEADER_BYTES.get(header_byte)

        if isinstance(device_type, tuple):
            device_type_idx = 0 if self.packet[start_idx + 2] in {0x00, 0x80, 0x02, 0x82} else 1
            return device_type[device_type_idx]
        if device_type is None and self.is_ec_condition(header_byte):
            return DeviceType.EC

        return device_type

    def get_packet_info(self, length: int, start_idx: int) -> tuple[PacketType, int]:
        """Determine packet type and sequence number."""
        packet_byte = self.packet[start_idx + (2 if length == 10 else 3)]
        seq_number = self.packet[start_idx + (3 if length == 10 else 4)]

        if packet_byte in {0x00, 0x01, 0x02, 0x11, 0x21}:
            return PacketType.QUERY, seq_number
        if packet_byte in {0x80, 0x82, 0x91, 0xA1, 0xB1}:
            return PacketType.RESPONSE, seq_number

        #LOGGER.debug(f"Unknown packet type: {hex(packet_byte)}")
        return PacketType.PROMPT, seq_number

    def parse_single_packet(self, start_idx: int) -> tuple[Packet | None, int]:
        """Parse a single packet."""
        if start_idx + 3 > len(self.packet) or self.packet[start_idx] != 0x02:
            return None, start_idx + 1

        header = self.packet[start_idx + 1]
        device_type = self.get_device_type(header, start_idx)
        length = self.get_packet_length(start_idx, device_type)
        
        if start_idx + length > len(self.packet):
            return None, len(self.packet)

        packet_data = self.packet[start_idx:start_idx + length]
        packet_type, seq_number = self.get_packet_info(length, start_idx)
        return BasePacket.Packet(device_type, packet_type, seq_number, packet_data), start_idx + length

    def parse_packets(self) -> list[Packet]:
        """Parse all packets in the packet."""
        packets = []

        while (start_idx := self.find_next_packet_start()) is not None:
            packet, next_idx = self.parse_single_packet(start_idx)
            if packet:
                packets.append(packet)

            # Update current position
            self.current_position = max(next_idx, self.current_position + 1)

        return packets
    

class DevicePacket:
    """Class to represent a device packet."""

    @dataclass
    class DeviceInfo:
        """Class to represent device information."""
        device_type: str
        room_id: str
        sub_id: str | None
        device_state: Any

        def __str__(self) -> str:
            return f"DeviceInfo(device_type={self.device_type}, room_id={self.room_id}, sub_id={self.sub_id}, device_state={self.device_state})"
    
    def __init__(self, cls, packet: BasePacket.Packet) -> None:
        """Initialize the device packet."""
        self.cls = cls
        self.packet = packet
        self.device_type = packet.device_type
        self.packet_type = packet.packet_type
        self.seq_number = packet.seq_number
        self.data = packet.data

    def parse(self) -> DeviceInfo | list[DeviceInfo] | None:
        """Parse the packet data based on the device type."""
        try:
            if self.device_type is None:
                LOGGER.error(f"Unknown device type at {self.data[1]:#x}: {self.data.hex()}")
                return None
            device_parse = getattr(self, f"parse_{self.device_type.value}", None)
            if device_parse is None:
                LOGGER.error(f"Device parsing method not found for {self.device_type.value}")
                return None
            return device_parse()
        except Exception as e:
            LOGGER.error(f"Error parsing {self.device_type.value} packet({e}): {self.data.hex()}")
            return None
    
    def parse_ec(self) -> list[DeviceInfo] | list:
        """Parse the packet data for EC devices."""
        device_infos = []
        data_length = len(self.data)
        ec_type: EcType = None

        if self.data[1] & 0xF0 == 0x30 and data_length != 30:
            device_infos.extend(self.parse_ec_3())
            ec_type = EcType.EC3
        elif self.data[1] & 0xF0 == 0x50:
            device_infos.extend(self.parse_ec_5())
            ec_type = EcType.EC5
        elif self.data[5] & 0xF0 == 0xE0 and data_length == 30:
            device_infos.extend(self.parse_ec_e())
            ec_type = EcType.ECE
        else:
            LOGGER.error(f"Unknown EC packet type at {self.data[1]:#x}: {self.data.hex()}")
        
        if ec_type and self.cls.entry.data.get(EC_TYPE) != ec_type:
            self.cls.hass.config_entries.async_update_entry(
                entry=self.cls.entry,
                data={**self.cls.entry.data, EC_TYPE: ec_type},
            )
            
        return device_infos
    
    def parse_ec_5(self) -> list[DeviceInfo]:
        """Parse the packet data for EC 5 devices."""
        device_infos = []
        
        for i in range(self.data[5]):
            device_infos.append(DevicePacket.DeviceInfo(
                device_type=DeviceType.LIGHT.value,
                room_id=str(self.data[1] & 0x0F),
                sub_id=str(i),
                device_state=bool(self.data[6] & (1 << i))
            ))
        for i in range(self.data[8]):
            base_index = 9 + 5 * i

            device_infos.extend([
                DevicePacket.DeviceInfo(
                    device_type=DeviceType.OUTLET.value,
                    room_id=str(self.data[1] & 0x0F),
                    sub_id=str(i),
                    device_state=self.data[base_index] in {0x21, 0x11}
                ),
                DevicePacket.DeviceInfo(
                    device_type=f"{DeviceType.OUTLET.value}:powerusage",
                    room_id=str(self.data[1] & 0x0F),
                    sub_id=f"power usage {str(i)}",
                    device_state=int.from_bytes(
                        self.data[base_index + 1:base_index + 3], 'big') / 10
                ),
                DevicePacket.DeviceInfo(
                    device_type=f"{DeviceType.OUTLET.value}:standbycutoff",
                    room_id=str(self.data[1] & 0x0F),
                    sub_id=f"standby cutoff {str(i)}",
                    device_state=self.data[base_index] in {0x11, 0x13, 0x12}
                )
            ])
        return device_infos
    
    def parse_ec_e(self) -> list[DeviceInfo]:
        """Parse the packet data for EC E devices."""
        device_infos = []

        if self.data[5] & 0x0F == 0x1:
            li, oi = 4, 3    # Light Iteration, Outlet Iteration
        else:
            li, oi = 2, 2
        
        for i in range(li):
            device_infos.append(DevicePacket.DeviceInfo(
                device_type=DeviceType.LIGHT.value,
                room_id=str(self.data[5] & 0x0F),
                sub_id=str(i),
                device_state=bool(self.data[6] & (0x1 << i))
            ))
            device_infos.append(DevicePacket.DeviceInfo(
                device_type=f"{DeviceType.LIGHT.value}:powerusage",
                room_id=str(self.data[5] & 0x0F),
                sub_id="power usage",
                device_state=int.from_bytes(self.data[12:14], byteorder='big') / 10
            ))
        for i in range(oi):
            device_infos.extend([
                DevicePacket.DeviceInfo(
                    device_type=DeviceType.OUTLET.value,
                    room_id=str(self.data[5] & 0x0F),
                    sub_id=str(i),
                    device_state=bool(self.data[7] & (0x1 << i))
                ),
                DevicePacket.DeviceInfo(
                    device_type=f"{DeviceType.OUTLET.value}:powerusage",
                    room_id=str(self.data[5] & 0x0F),
                    sub_id=f"power usage {str(i)}",
                    device_state=int.from_bytes(
                        self.data[14 + 2 * i: 16 + 2 * i], byteorder='big') / 10
                ),
                DevicePacket.DeviceInfo(
                    device_type=f"{DeviceType.OUTLET.value}:standbycutoff",
                    room_id=str(self.data[5] & 0x0F),
                    sub_id=f"standby cutoff",
                    device_state=bool(self.data[7] >> 4 & 1)
                ),
            ])
            if i <= 1:
                device_infos.append(DevicePacket.DeviceInfo(
                    device_type=f"{DeviceType.OUTLET.value}:cutoffvalue",
                    room_id=str(self.data[5] & 0x0F),
                    sub_id=f"cutoff value {str(i)}",
                    device_state=int.from_bytes(
                        self.data[8 + 2 * i: 10 + 2 * i], byteorder='big') / 10
                ))

        return device_infos
    
    def parse_energy(self) -> list[DeviceInfo] | list:
        """Parse the packet data for energy devices."""
        device_infos = []
        start_idx = 7
        
        for _ in range(self.data[6]):
            energy_id = self.data[start_idx]
            increment = 1 if (energy_id >> 4) & 0xF == 0x8 else 8

            if increment == 1:
                LOGGER.debug(f"Energy ID {energy_id & 0x0F} is not active, skipping...")
                start_idx += increment
                continue
            
            try:
                energy_type = EnergyType(energy_id & 0x0F)
            except ValueError:
                LOGGER.warning(f"Unknown energy type {energy_id & 0x0F}, skipping...")
                start_idx += increment
                continue

            data_mapping = {
                EnergyMetric.TOTAL: float(self.data[start_idx + 1:start_idx + 5].hex()),
                EnergyMetric.REALTIME: int(self.data[start_idx + 6:start_idx + 8].hex()),
            }
            for sub_id, device_state in data_mapping.items():
                device_info = DevicePacket.DeviceInfo(
                    device_type=f"{DeviceType.ENERGY.value}:{sub_id.value}usage",
                    room_id=energy_type.name.lower(),
                    sub_id=f"{sub_id.value} usage",
                    device_state=ENERGY_TO_VALUE.get((energy_type, sub_id), lambda val, _: val)(
                        device_state, increment
                    ),
                )
                device_infos.append(device_info)
            start_idx += increment
            
        return device_infos
    
    def parse_iaq(self) -> list[DeviceInfo]:
        """Parse the packet data for IAQ devices."""

    def parse_ignore(self) -> DeviceInfo:
        """Parse the packet data for ignore devices."""
    
    def parse_fan(self) -> list[DeviceInfo]:
        """Parse the packet data for a fan."""
        device_infos = []
        
        if len(self.data) != 10:
            LOGGER.error(f"Unexpected packet length ({len(self.data)}) for fan packet: {self.data.hex()}")
            return None
        
        device_infos.append(DevicePacket.DeviceInfo(
            device_type=DeviceType.FAN.value,
            room_id=str(self.data[4]),
            sub_id=None,
            device_state={
                ATTR_STATE: bool(self.data[5] & 0x01),
                "natural_state": bool(self.data[5] >> 4 & 1),
                WIND_SPEED: self.data[6],
            }
        ))
        device_infos.append(DevicePacket.DeviceInfo(
            device_type=f"{DeviceType.FAN.value}:timer",
            room_id=str(self.data[4]),
            sub_id="timer",
            device_state={
                ATTR_STATE: self.data[7],
                ATTR_MIN: 0,
                ATTR_MAX: 240,
                ATTR_STEP: 10,
            }
        ))
        return device_infos
    
    def parse_gas(self) -> DeviceInfo:
        """""Parse the packet data for a gas."""
        if len(self.data) != 10:
            LOGGER.error(f"Unexpected packet length ({len(self.data)}) for gas packet: {self.data.hex()}")
            return None
        return DevicePacket.DeviceInfo(
            device_type=DeviceType.GAS.value,
            room_id=str(self.data[4]),
            sub_id=None,
            device_state=bool(self.data[5])
        )
    
    def parse_doorlock(self) -> DeviceInfo:
        """Parse the packet data for a doorlock."""
        if len(self.data) != 10:
            LOGGER.error(f"Unexpected packet length ({len(self.data)}) for doorlock packet: {self.data.hex()}")
            return None
        return DevicePacket.DeviceInfo(
            device_type=DeviceType.DOORLOCK.value,
            room_id=str(self.data[4]),
            sub_id=None,
            device_state=bool(self.data[5] & 0xAE)
        )
    
    def parse_thermostat(self) -> list[DeviceInfo]:
        """Parse the packet data for thermostat devices."""
        device_infos = []
        data_length = len(self.data)

        if data_length == 14:
            device_infos.append(DevicePacket.DeviceInfo(
                device_type="heatwater:set",
                room_id=str(self.data[5]),
                sub_id="set",
                device_state={
                    ATTR_MIN: self.data[6],
                    ATTR_MAX: self.data[7],
                    ATTR_STATE: self.data[8],
                    ATTR_STEP: 5,
                }
            ))
            device_infos.append(DevicePacket.DeviceInfo(
                device_type="hotwater:set",
                room_id=str(self.data[5]),
                sub_id="set",
                device_state={
                    ATTR_MIN: self.data[9],
                    ATTR_MAX: self.data[10],
                    ATTR_STATE: self.data[11],
                    ATTR_STEP: 1,
                }
            ))
        elif data_length == 16:
            device_infos.append(DevicePacket.DeviceInfo(
                device_type=DeviceType.THERMOSTAT.value,
                room_id=str(self.data[5] & 0x0F),
                sub_id=None,
                device_state={
                    ATTR_STATE: bool(self.data[6] & 0x01),
                    SERVICE_SET_TEMPERATURE: (self.data[7] & 0x3F) + (self.data[7] & 0x40 > 0) * 0.5,
                    ATTR_CURRENT_TEMPERATURE: int.from_bytes(self.data[8:10], byteorder='big') / 10.0,
                }
            ))
        else:
            LOGGER.debug(f"Unexpected packet length ({len(self.data)}) for thermostat packet: {self.data.hex()}")

        return device_infos
    