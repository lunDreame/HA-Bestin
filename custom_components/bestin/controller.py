"""Controller for Bestin devices."""

from __future__ import annotations

import asyncio
from typing import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .packet_handler import BasePacket, DevicePacket, PacketType, EcType
from .command_handler import CommandPacket
from .const import (
    LOGGER,
    EC_TYPE,
    SEND_RETRY,
    DEVICE_TYPE,
    SUB_TYPE,
    ROOM_ID,
    SUB_ID,
    VALUE,
    SEQ_NUMBER,
    BRAND_PREFIX,
    DEVICE_PLATFORM_MAP,
    PLATFORM_SIGNAL_MAP,
    Device,
    DeviceInfo,
)


class BestinController:
    """Controller for managing Bestin devices and communication."""

    def __init__(
        self, 
        hass: HomeAssistant,
        entry: ConfigEntry,
        entity_groups: dict[str, set[str]],
        host: str, 
        connection,
        add_device_callback: Callable,
    ) -> None:
        """Initialize the BestinController."""
        self.hass = hass
        self.entry = entry
        self.entity_groups = entity_groups
        self.host = host
        self.connection = connection
        self.add_device_callback = add_device_callback

        self.devices: dict[str, Device] = {}
        self.packet: BasePacket.Packet = None
        self.queue: list[dict] = []
        self.tasks: list[asyncio.Task] = []
        self.send_retry: int = 10
        self.delay_9600 = [0.005, 0.01, 0.02, 0.04, 0.08]
        self.delay_38400 = [0.002, 0.005, 0.01, 0.02, 0.04]
        self.tx_wait_time = 0.02
        self.min_wait_time = 0.01

    async def start(self) -> None:
        """Start the tasks."""
        self.tasks = [
            asyncio.create_task(self.handle_receive_data()),
            asyncio.create_task(self.handle_queue()),
        ]

    async def stop(self) -> None:
        """Stop the tasks."""
        for task in self.tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks = []
    
    @property
    def available(self) -> bool:
        """Return True if the connection is available."""
        if self.connection and self.connection.is_connected():
            return True
        return True
    
    async def receive_data(self, size: int = 1024) -> bytes | None:
        """Return the receive data."""
        if self.available:
            return await self.connection.receive(size)
    
    async def send_data(self, packet: bytearray) -> None:
        """Send data to the connection."""
        if self.available:
            await self.connection.send(packet)
    
    def makesum(self, packet: bytearray) -> int:
        """Make the checksum of a packet"""
        checksum = 3
        for i in range(len(packet) - 1):
            checksum ^= packet[i]
            checksum = (checksum + 1) & 0xFF
        return checksum
    
    def checksum(self, packet: bytes) -> bool:
        """Check the checksum of a packet"""
        if len(packet) < 6:
            return False
        
        checksum = 3
        for byte in packet[:-1]:
            checksum ^= byte
            checksum = (checksum + 1) & 0xFF
        return checksum == packet[-1]
    
    def enqueue(self, task_data: dict) -> None:
        """Add a task to the queue."""
        self.queue.append(task_data)
        LOGGER.debug(f"Task enqueued: {task_data}")

    def dequeue(self) -> dict | None:
        """Remove and return a task from the queue."""
        try:
            return self.queue.pop(0)
        except IndexError:
            return None
        
    def get_ec_type(self) -> EcType:
        """Return the EC type of the energy packet."""
        return self.entry.data.get(EC_TYPE, EcType.ECE)
    
    def get_devices_from_domain(self, domain: str) -> list:
        """Get devices from a specific domain"""
        entity_list = self.entity_groups.get(domain, [])
        return [self.devices.get(unique_id, {}) for unique_id in entity_list]
    
    @callback
    def set_command(self, device: Device, value, **kwargs) -> None:
        """Set command to a device."""
        dev_info = device.dev_info
        seq_number = getattr(self.packet, SEQ_NUMBER, 0) + 1
        if ":" in dev_info.device_type:
            device_type, sub_type = dev_info.device_type.split(":")
        else:
            device_type, sub_type = dev_info.device_type, None
            
        if kwargs:
            sub_type, value = next(iter(kwargs.items()))
            
        que_task = {
            SEND_RETRY: 0,
            DEVICE_TYPE: device_type,
            SUB_TYPE: sub_type,
            ROOM_ID: dev_info.room_id,
            SUB_ID: dev_info.sub_id,
            VALUE: value,
            SEQ_NUMBER: seq_number,
        }
        LOGGER.debug(f"Create que task: {que_task}")
        self.enqueue(que_task)
        
    def init_device(
        self, packet: BasePacket.Packet, device_info: DevicePacket.DeviceInfo
    ) -> Device:
        """Initialize a device."""
        if ":" in device_info.device_type:
            device_type, sub_type = device_info.device_type.split(":")
        else:
            device_type, sub_type = device_info.device_type, None
        sub_id = device_info.sub_id
        room_id = device_info.room_id
        device_id = f"{BRAND_PREFIX}_{device_type}_{room_id}"
        device_name = f"{device_type} {room_id}"
        
        if sub_id:
            sub_id_cleaned = sub_id.replace(" ", "_")
            device_id += f"_{sub_id_cleaned}"
            device_name += f" {sub_id}"
    
        unique_id = f"{device_id}-{self.host}"
    
        if device_id not in self.devices:
            dev_info = DeviceInfo(
                device_id=device_id,
                device_name=device_name.title(),
                device_type=device_info.device_type,
                sub_type=sub_type,
                room_id=room_id,
                sub_id=sub_id,
                device_state=device_info.device_state,
            )
            self.devices[device_id] = Device(
                set_command=self.set_command,
                domain=DEVICE_PLATFORM_MAP[dev_info.device_type],
                unique_id=unique_id,
                dev_info=dev_info,
            )
        return self.devices[device_id]
    
    def set_device(
        self, packet: BasePacket.Packet, device_info: DevicePacket.DeviceInfo
    ) -> None:
        """Set a device."""
        if (device_type := device_info.device_type) not in DEVICE_PLATFORM_MAP:
            LOGGER.warning(f"Unknown device type: {device_type}")
            return
        
        device = self.init_device(packet, device_info)
        dev_info = device.dev_info

        device_platform = DEVICE_PLATFORM_MAP[device_type]
        platform_signal = PLATFORM_SIGNAL_MAP[device_platform]
        self.add_device_callback(platform_signal, device)

        if dev_info.device_state != device_info.device_state:
            dev_info.device_state = device_info.device_state
            device.update_callback()
        
        if packet.packet_type == PacketType.PROMPT and self.queue:
            que_data = self.queue[0]
            if (
                que_data.get(DEVICE_TYPE) == dev_info.device_type
                and que_data.get(ROOM_ID) == dev_info.room_id
                and que_data.get(SUB_ID) == dev_info.sub_id
            ):
                self.dequeue()
            
    def handle_packet(self, packet: BasePacket.Packet) -> None:
        """Handle a packet."""
        if packet.packet_type in {PacketType.RESPONSE, PacketType.PROMPT}:
            device_info = DevicePacket(self, packet).parse()
            if device_info:
                if isinstance(device_info, list):
                    for info in device_info:
                        self.set_device(packet, info)
                else:
                    self.set_device(packet, device_info)
                    
    async def handle_queue_data(self, que_data: dict) -> None:
        """Handle queue data."""
        retry_delays = self.delay_38400 if self.get_ec_type() == EcType.EC3 else self.delay_9600

        command_packet = CommandPacket(
            cls=self,
            device_type=que_data.get(DEVICE_TYPE),
            sub_type=que_data.get(SUB_TYPE),
            room_id=que_data.get(ROOM_ID),
            sub_id=que_data.get(SUB_ID),
            value=que_data.get(VALUE),
            seq_number=que_data.get(SEQ_NUMBER),
        ).create_packet()

        if command_packet is None:
            LOGGER.warning("Failed to create command packet.")
            self.dequeue()
            return

        command_packet[-1] = self.makesum(command_packet)
        if not self.checksum(command_packet):
            LOGGER.error("Checksum validation failed for command packet.")
            self.dequeue()
            return

        que_data[SEND_RETRY] += 1
        que_data[SEQ_NUMBER] += 1

        await asyncio.sleep(self.tx_wait_time)

        try:
            await self.send_data(command_packet)
            LOGGER.info(f"Send attempt {que_data[SEND_RETRY]} successful: {command_packet.hex()}")
        except Exception as e:
            LOGGER.error(f"Error while sending packet: {e}")
            self.dequeue()
            return

        if que_data[SEND_RETRY] >= self.send_retry:
            LOGGER.info(
                f"Packet send failed after {que_data[SEND_RETRY]} attempts: {command_packet.hex()}"
            )
            self.dequeue()
            return
        
        delay_index = min(que_data[SEND_RETRY] - 1, len(retry_delays) - 1)
        current_delay = max(retry_delays[delay_index] * (1.1 ** que_data[SEND_RETRY]), self.min_wait_time)
        await asyncio.sleep(current_delay)

        if que_data[SEND_RETRY] < self.send_retry:
            LOGGER.debug(f"Packet re-enqueued after {que_data[SEND_RETRY]} attempts.")
            #self.enqueue(que_data)
        else:
            LOGGER.info(f"Packet successfully handled after {que_data[SEND_RETRY]} attempts.")
            
    async def handle_receive_data(self) -> None:
        """Handle the receive data."""
        while True:
            if not self.available:
                await asyncio.sleep(0.1)
                continue
            
            try:
                received_data = await self.receive_data()
                if not received_data:
                    await asyncio.sleep(0.02)
                    continue

                packets = BasePacket(received_data).parse_packets()
                for packet in packets:
                    if self.checksum(packet.data):
                        self.packet = packet
                        self.handle_packet(packet)
            except Exception as ex:
                LOGGER.error(f"Error in handle_receive_data: {ex}", exc_info=True)
                
            await asyncio.sleep(0.02)
            
    async def handle_queue(self) -> None:
        """Handle the queue."""
        while True:
            try: 
                if not self.queue:
                    await asyncio.sleep(0.1)
                    continue
                que_data = self.queue[0]
                await self.handle_queue_data(que_data)
            except Exception as ex:
                LOGGER.error(f"Error in handle_queue: {ex}", exc_info=True)
