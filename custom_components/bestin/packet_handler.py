"""Packet handler for Bestin devices."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from homeassistant.const import ATTR_STATE, WIND_SPEED
from homeassistant.components.light import ATTR_BRIGHTNESS, ATTR_COLOR_TEMP
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
        0x30: DeviceType.IGNORE,
        0x31: (DeviceType.GAS, DeviceType.EC),
        0x32: DeviceType.IGNORE,
        0x41: (DeviceType.DOORLOCK, DeviceType.IGNORE),
        0x42: DeviceType.IGNORE,
        0x61: DeviceType.FAN,
        0xB1: DeviceType.IGNORE,
        0xB2: DeviceType.IGNORE,
        0xB3: DeviceType.IGNORE,
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
        upper_nibble, lower_nibble = header_byte >> 4, header_byte & 0x0F
        if upper_nibble == 0x3:
            return lower_nibble == 0xF or 0x1 <= lower_nibble <= 0x5
        elif upper_nibble == 0x5:
            return 0x1 <= lower_nibble <= 0x5
        return False

    def get_device_type(self, header_byte: int, start_idx: int) -> DeviceType | None:
        """Determine device type based on header byte and packet type."""
        device_type = self.HEADER_BYTES.get(header_byte)
        packet_type = self.packet[start_idx + 2]
        is_fixed = packet_type in {0x00, 0x80, 0x02, 0x82}
        
        if isinstance(device_type, tuple):
            return device_type[0] if is_fixed else device_type[1]
        if device_type is None or (
            device_type == DeviceType.IGNORE and not is_fixed
        ):
            if self.is_ec_condition(header_byte):
                return DeviceType.EC
            
        return device_type
    
    def get_packet_info(self, start_idx: int, device_type: DeviceType, length: int) -> tuple[PacketType, int]:
        """Determine packet type and sequence number."""
        packet_byte = self.packet[start_idx + (2 if length == 10 else 3)]
        seq_number = self.packet[start_idx + (3 if length == 10 else 4)]
        
        if device_type == DeviceType.EC:
            if packet_byte in {0x01, 0x12, 0x03, 0x31, 0x11, 0x06, 0x05, 0x02}:
                return PacketType.QUERY, seq_number
            elif packet_byte in {0x81, 0x92, 0x83, 0xB1, 0x91, 0x86, 0x85, 0x82}:
                return PacketType.RESPONSE, seq_number
        else:
            if packet_byte in {0x00, 0x21, 0x02, 0x01, 0x11, 0x05}:
                return PacketType.QUERY, seq_number
            elif packet_byte in {0x80, 0xA1, 0x82, 0x81, 0x91, 0x85}:
                return PacketType.RESPONSE, seq_number
            
        LOGGER.debug(f"Packet type: {hex(packet_byte)}, {self.packet.hex()}")
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
        packet_type, seq_number = self.get_packet_info(start_idx, device_type, length)
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
            parse_method = getattr(self, f"parse_{self.device_type.value}", None)
            if parse_method is None:
                LOGGER.error(f"Device parsing method not found for {self.device_type.value}")
                return None
            return parse_method()
        except Exception as e:
            LOGGER.error(f"Error parsing {self.device_type.value} packet({e}): {self.data.hex()}")
            return None
    
    def parse_ec(self) -> list[DeviceInfo] | list:
        """Parse the packet data for EC devices."""
        device_infos = []
        data_length = len(self.data)
        ec_type: EcType = None

        if self.data[1] & 0xF0 == 0x30 and data_length != 30:
            ec_type = EcType.EC3
            parse_method = getattr(self, f"parse_ec3_{self.data[3]:x}", None)
            if parse_method is None:
                LOGGER.debug(f"No response packet {self.data[3]:#x} parsing method found for EC type 3: {self.data.hex()}")
                return []
            device_infos.extend(parse_method())
        elif self.data[1] & 0xF0 == 0x50:
            ec_type = EcType.EC5
            device_infos.extend(self.parse_ec_5())
        elif self.data[5] & 0xF0 == 0xE0 and data_length == 30:
            ec_type = EcType.ECE
            device_infos.extend(self.parse_ec_e())
        else:
            LOGGER.error(f"Unknown EC packet type at {self.data[1]:#x}: {self.data.hex()}")
        
        if ec_type and self.cls.entry.data.get(EC_TYPE) != ec_type:
            self.cls.hass.config_entries.async_update_entry(
                entry=self.cls.entry,
                data={**self.cls.entry.data, EC_TYPE: ec_type},
            )
            
        return device_infos
    
    def parse_ec3_91(self) -> list[DeviceInfo]:
        """Parse the packet data for EC 3 0x91 devices."""
        device_infos = []

        # Variables
        lc = self.data[10] & 0xF          # Light count
        oc = self.data[11]                # Outlet count
        lb = (self.data[10] >> 4) == 0x4  # Light block
        lbc = lc + 1 if lb else lc        # Light block count

        # Define light_idx after lbc is calculated
        light_idx = 17
        outlet_idx = light_idx + lbc * 13  # Start index

        for _ in range(lc):
            lidx = self.data[light_idx]
            if lidx >> 4 == 0x8:
                LOGGER.debug(f"Light {self.data[1] & 0xF}-{lidx & 0xF} is a block light")
                light_idx += 13
                continue

            device_infos.extend([
                DevicePacket.DeviceInfo(
                    device_type=DeviceType.DIMMING.value,
                    room_id=str(self.data[1] & 0xF),
                    sub_id=str(lidx & 0xF),
                    device_state={
                        ATTR_STATE: self.data[light_idx + 1] == 0x01,
                        ATTR_BRIGHTNESS: self.data[light_idx + 2],
                        ATTR_COLOR_TEMP: self.data[light_idx + 3],
                    }
                ),
                DevicePacket.DeviceInfo(
                    device_type=f"{DeviceType.DIMMING.value}:powerusage",
                    room_id=str(self.data[1] & 0xF),
                    sub_id="power usage",
                    device_state=int.from_bytes(self.data[12:14], 'big') / 10.0
                ),
                DevicePacket.DeviceInfo(
                    device_type=f"{DeviceType.DIMMING.value}:cumulativeusage",
                    room_id=str(self.data[1] & 0xF),
                    sub_id="cumulative usage",
                    device_state=int.from_bytes(self.data[14:17], 'big')
                ),
            ])
            light_idx += 13

        for _ in range(oc):
            oidx = self.data[outlet_idx]
            if oidx >> 4 == 0x8:
                LOGGER.debug(f"Outlet {self.data[1] & 0xF}-{oidx & 0xF} is a block outlet")
                outlet_idx += 14
                continue

            device_infos.extend([
                DevicePacket.DeviceInfo(
                    device_type=DeviceType.OUTLET.value,
                    room_id=str(self.data[1] & 0x0F),
                    sub_id=str(oidx & 0xF),
                    device_state=bool(self.data[outlet_idx + 1] & 0x1)
                ),
                DevicePacket.DeviceInfo(
                    device_type=f"{DeviceType.OUTLET.value}:standbycutoff",
                    room_id=str(self.data[1] & 0x0F),
                    sub_id=f"standby cutoff {str(oidx & 0xF)}",
                    device_state=bool(self.data[outlet_idx + 1] & 0x10)
                ),
                DevicePacket.DeviceInfo(
                    device_type=f"{DeviceType.OUTLET.value}:cutoffvalue",
                    room_id=str(self.data[1] & 0x0F),
                    sub_id=f"cutoff value {str(oidx & 0xF)}",
                    device_state=int.from_bytes(self.data[outlet_idx + 7:outlet_idx + 9], 'big') / 10.0
                ),
                DevicePacket.DeviceInfo(
                    device_type=f"{DeviceType.OUTLET.value}:powerusage",
                    room_id=str(self.data[1] & 0x0F),
                    sub_id=f"power usage {str(oidx & 0xF)}",
                    device_state=(
                        int.from_bytes(self.data[outlet_idx + 9:outlet_idx + 11], 'big') / 10.0
                        if oidx % 2 == 0 else
                        int.from_bytes(self.data[outlet_idx + 2:outlet_idx + 4], 'big') / 10.0
                    )
                ),
                DevicePacket.DeviceInfo(
                    device_type=f"{DeviceType.OUTLET.value}:cumulativeusage",
                    room_id=str(self.data[1] & 0x0F),
                    sub_id=f"cumulative usage {str(oidx & 0xF)}",
                    device_state=(
                        int.from_bytes(self.data[outlet_idx + 11:outlet_idx + 14], 'big')
                        if oidx % 2 == 0 else
                        int.from_bytes(self.data[outlet_idx + 4:outlet_idx + 7], 'big')
                    )
                ),
            ])
            outlet_idx += 14

        return device_infos
    
    def parse_ec_5(self) -> list[DeviceInfo]:
        """Parse the packet data for EC 5 devices."""
        device_infos = []
        
        for i in range(self.data[5]):
            device_infos.append(DevicePacket.DeviceInfo(
                device_type=DeviceType.LIGHT.value,
                room_id=str(self.data[1] & 0xF),
                sub_id=str(i),
                device_state=bool(self.data[6] & (1 << i))
            ))
        for i in range(self.data[8]):
            base_index = 9 + 5 * i

            device_infos.extend([
                DevicePacket.DeviceInfo(
                    device_type=DeviceType.OUTLET.value,
                    room_id=str(self.data[1] & 0xF),
                    sub_id=str(i),
                    device_state=self.data[base_index] in {0x21, 0x11}
                ),
                DevicePacket.DeviceInfo(
                    device_type=f"{DeviceType.OUTLET.value}:powerusage",
                    room_id=str(self.data[1] & 0xF),
                    sub_id=f"power usage {str(i)}",
                    device_state=int.from_bytes(
                        self.data[base_index + 1:base_index + 3], 'big') / 10.0
                ),
                DevicePacket.DeviceInfo(
                    device_type=f"{DeviceType.OUTLET.value}:standbycutoff",
                    room_id=str(self.data[1] & 0xF),
                    sub_id=f"standby cutoff {str(i)}",
                    device_state=self.data[base_index] in {0x11, 0x13, 0x12}
                )
            ])
        return device_infos
    
    def parse_ec_e(self) -> list[DeviceInfo]:
        """Parse the packet data for EC E devices."""
        device_infos = []

        if self.data[5] & 0xF == 0x1:
            li, oi = 4, 3    # Light Iteration, Outlet Iteration
        else:
            li, oi = 2, 2
        
        for i in range(li):
            device_infos.append(DevicePacket.DeviceInfo(
                device_type=DeviceType.LIGHT.value,
                room_id=str(self.data[5] & 0xF),
                sub_id=str(i),
                device_state=bool(self.data[6] & (0x1 << i))
            ))
            device_infos.append(DevicePacket.DeviceInfo(
                device_type=f"{DeviceType.LIGHT.value}:powerusage",
                room_id=str(self.data[5] & 0xF),
                sub_id="power usage",
                device_state=int.from_bytes(self.data[12:14], 'big') / 10.0
            ))
        for i in range(oi):
            device_infos.extend([
                DevicePacket.DeviceInfo(
                    device_type=DeviceType.OUTLET.value,
                    room_id=str(self.data[5] & 0xF),
                    sub_id=str(i),
                    device_state=bool(self.data[7] & (0x1 << i))
                ),
                DevicePacket.DeviceInfo(
                    device_type=f"{DeviceType.OUTLET.value}:powerusage",
                    room_id=str(self.data[5] & 0xF),
                    sub_id=f"power usage {str(i)}",
                    device_state=int.from_bytes(self.data[14 + 2 * i: 16 + 2 * i], 'big') / 10.0
                ),
                DevicePacket.DeviceInfo(
                    device_type=f"{DeviceType.OUTLET.value}:standbycutoff",
                    room_id=str(self.data[5] & 0xF),
                    sub_id=f"standby cutoff",
                    device_state=bool(self.data[7] >> 4 & 1)
                ),
            ])
            if i <= 1:
                device_infos.append(DevicePacket.DeviceInfo(
                    device_type=f"{DeviceType.OUTLET.value}:cutoffvalue",
                    room_id=str(self.data[5] & 0xF),
                    sub_id=f"cutoff value {str(i)}",
                    device_state=int.from_bytes(self.data[8 + 2 * i: 10 + 2 * i], 'big') / 10.0
                ))

        return device_infos
    
    def parse_energy(self) -> list[DeviceInfo] | list:
        """Parse the packet data for energy devices."""
        device_infos = []
        start_idx = 7
        
        for _ in range(self.data[6]):
            energy_id = self.data[start_idx]
            increment = 1 if energy_id >> 4 == 0x8 else 8

            if increment == 1:
                LOGGER.debug(f"Energy ID {energy_id & 0xF} is not active, skipping...")
                start_idx += increment
                continue
            
            try:
                energy_type = EnergyType(energy_id & 0xF)
            except ValueError:
                LOGGER.warning(f"Unknown energy type {energy_id & 0xF}, skipping...")
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
            LOGGER.warning(f"Unexpected packet length ({len(self.data)}) for fan packet: {self.data.hex()}")
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
            LOGGER.warning(f"Unexpected packet length ({len(self.data)}) for gas packet: {self.data.hex()}")
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
            LOGGER.warning(f"Unexpected packet length ({len(self.data)}) for doorlock packet: {self.data.hex()}")
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
                room_id=str(self.data[5] & 0xF),
                sub_id=None,
                device_state={
                    ATTR_STATE: bool(self.data[6] & 0x1),
                    SERVICE_SET_TEMPERATURE: (self.data[7] & 0x3F) + (self.data[7] & 0x40 > 0) * 0.5,
                    ATTR_CURRENT_TEMPERATURE: int.from_bytes(self.data[8:10], 'big') / 10.0,
                }
            ))
        else:
            LOGGER.warning(f"Unexpected packet length ({len(self.data)}) for thermostat packet: {self.data.hex()}")

        return device_infos
    