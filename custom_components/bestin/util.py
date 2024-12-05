"""Utilities for Bestin devices."""

from __future__ import annotations

import re

def check_ip_or_serial(host: str) -> bool:
    """Check if the given host is an IP address or a serial port."""
    ip_pattern = re.compile(r"^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$")
    serial_pattern = re.compile(r"/dev/tty(USB|AMA)\d+")

    if ip_pattern.match(host) or serial_pattern.match(host):
        return True
    else:
        return False

def remove_colon(device_type: str) -> str:
    """Remove the colon from the device type."""
    if ":" in device_type:
        return device_type.split(":")[0].title()
    return device_type.title()
