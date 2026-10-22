"""Low-level Python driver for the SCHOTT ColdVision CV-LS light source.

The CV-LS accepts an ASCII protocol over an Ethernet socket (default port 50811). 
Every command is a string that starts with `&` and ends with a 
carriage return `\r`; the unit replies with `&` followed by the
command and the requested value. See the SCHOTT ColdVision Light Source 
Programming Guide (D20980.026) for the full command set.
"""

from __future__ import annotations

import socket
from typing import Union

from hardware_device_base import HardwareDeviceBase


class ColdVisionError(RuntimeError):
    """Raised when the CV-LS rejects a command or a transaction fails."""


class ColdVisionNack(ColdVisionError):
    """Raised when the CV-LS replies with a negative acknowledgement."""


class ColdVision(HardwareDeviceBase):
    """A driver class for the SCHOTT ColdVision CV-LS light source."""

    DEFAULT_PORT = 50811

    def __init__(
        self,
        log: bool = True,
        logfile: str = __name__.rsplit(".", 1)[-1],
    ) -> None:
        super().__init__(log, logfile)
        self.sock: socket.socket | None = None
        self.product_name: str | None = None
        self.model: str | None = None
        self.serial_number: str | None = None
        self.firmware_revision: str | None = None

    def connect(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        timeout: float = 2.0,
    ) -> None:
        """Open the CV-LS socket (Port 50811 by default)"""
        if self.is_connected():
            self.disconnect()

        self.report_info(f"Connecting to ColdVision at {host}:{port}...")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
        except OSError as exc:
            sock.close()
            self.report_error(f"Could not connect to {host}:{port}: {exc}")
            raise ConnectionError(f"Could not connect to {host}:{port}") from exc

        self.sock = sock
        self._set_connected(True)
        self.report_info("ColdVision connected")

    def disconnect(self) -> None:
        """Close the socket connection to the CV-LS"""
        if self.sock is not None:
            self.sock.close()
        self.sock = None
        self._set_connected(False)
        self.report_info("ColdVision disconnected")

    def initialize(self) -> bool:
        """Query identification info to confirm the connected unit

        The product name is required; model, serial number and firmware
        revision are best-effort, since not every unit/firmware supports
        every query. Fields the unit rejects are left as None.

        :return: True if identification succeeded, False otherwise
        """
        try:
            self.product_name = self.get_product_name()
            self.model = self._query_optional(self.get_model, "model")
            self.serial_number = self._query_optional(
                self.get_serial_number, "serial number"
            )
            self.firmware_revision = self._query_optional(
                self.get_firmware_revision, "firmware revision"
            )
        except ColdVisionError as exc:
            self.report_error(f"Initialization failed: {exc}")
            self.initialized = False
            return False
        self.report_info(
            f"Initialized {self.product_name} model {self.model} "
            f"serial {self.serial_number}, firmware {self.firmware_revision}"
        )
        self.initialized = True
        return True

    def _query_optional(self, getter, name: str) -> str | None:
        """Run an identification query, returning None if the unit NACKs it."""
        try:
            return getter()
        except ColdVisionNack as exc:
            self.report_warning(f"Unit does not support {name} query: {exc}")
            return None

    def get_product_name(self) -> str:
        """Return the product name string, e.g. "SCHOTT ColdVision Light Source"."""
        return self._transact("Q")

    def get_firmware_revision(self) -> str:
        """Return the firmware revision string, e.g. "1.23"."""
        return self._transact("F?")

    def get_serial_number(self) -> str:
        """Return the unit's 6 digit serial number"""
        return self._transact("Z?")

    def get_model(self) -> str:
        """Return the unit's model string.

        The unit reports model and serial together as "Y:XXXXXX"; only the
        model part is returned.
        """
        return self._transact("ZF?").rsplit(":", 1)[0]

    def get_power(self, channel: int = 0) -> int:
        """Get the output power limit for a channel.

        :param channel: 0 = Common, 1-4 = individual channel.
        :return: Power in the range 0-1000.
        """
        return int(self._transact(f"I{channel},?"))

    def set_power(self, value: int, channel: int = 0) -> int:
        """Set the output power limit for a channel

        :param value: Power in the range 0-1000
        :param channel: 0 = Common, 1-4 = individual channel
        :return: The power value acknowledged by the unit
        """
        if not 0 <= value <= 1000:
            raise ValueError("value must be between 0 and 1000")
        return int(self._transact(f"I{channel},{value}"))

    def get_enabled(self, channel: int = 0) -> bool:
        """Get whether the LED control loop is active for a channel

        :param channel: 0 = Common, 1-4 = individual channel
        """
        return self._transact(f"L{channel},?") == "1"

    def set_enabled(self, enabled: bool, channel: int = 0) -> bool:
        """Enable or disable the LED control loop for a channel

        :param enabled: True to enable, False to disable
        :param channel: 0 = Common, 1-4 = individual channel
        :return: The enabled state acknowledged by the unit
        """
        return self._transact(f"L{channel},{int(enabled)}") == "1"

    def get_equalizer_enabled(self) -> bool:
        """Get whether the closed-loop light equalizer is enabled."""
        return self._transact("E?") == "1"

    def set_equalizer_enabled(self, enabled: bool) -> bool:
        """Enable or disable the closed-loop light equalizer

        :param enabled: True to enable, False to disable
        :return: The enabled state acknowledged by the unit
        """
        return self._transact(f"E{int(enabled)}", name="E") == "1"

    def get_equalizer_status(self) -> int:
        """Return the equalizer stability code.

        0 = Not stable, 1 = Locked (stable), 2 = Waiting for start-up delay,
        4 = Intensity low, 6 = Intensity high,
        8 = Over range (intensity too low to maintain stability),
        10 = Under range (intensity too high to maintain stability).
        """
        return int(self._transact("ES?"))

    def is_equalizer_locked(self) -> bool:
        """Return True if the equalizer control loop is locked (stable)."""
        return self.get_equalizer_status() == 1

    def get_equalizer_target(self) -> int:
        """Get the equalizer target light output.

        :return: Target in the range 0-4095
        """
        return int(self._transact("EE?"), 16)

    def set_equalizer_target(self, value: int) -> int:
        """Set the equalizer target light output

        :param value: Target in the range 0-4095
        :return: The target acknowledged by the unit
        """
        if not 0 <= value <= 4095:
            raise ValueError("value must be between 0 and 4095")
        return int(self._transact(f"EE{value:03X}", name="EE"), 16)

    def get_equalizer_feedback(self) -> int:
        """Return the time-averaged light feedback used by the equalizer (0-4095)."""
        return int(self._transact("EV?"), 16)

    def get_equalizer_output(self) -> int:
        """Return the current output power of the equalizer loop (0-4095)."""
        return int(self._transact("ED?"), 16)

    def get_equalizer_delay(self) -> int:
        """Get the start-up delay before the equalizer takes control (0-500)."""
        return int(self._transact("EI?"))

    def set_equalizer_delay(self, value: int) -> int:
        """Set the start-up delay before the equalizer takes control

        :param value: Delay in the range 0-500
        :return: The delay acknowledged by the unit
        """
        if not 0 <= value <= 500:
            raise ValueError("value must be between 0 and 500")
        return int(self._transact(f"EI{value}", name="EI"))

    def get_led_temperature(self) -> float:
        """Return the LED PCB temperature in Celsius."""
        return float(self._transact("?LT"))

    def get_board_temperature(self) -> float:
        """Return the main PCB temperature in Celsius."""
        return float(self._transact("?BT"))

    def get_fan_speed(self) -> int:
        """Return the current fan speed in RPM."""
        return int(self._transact("?G"))

    def get_error_flags(self) -> int:
        """Return the system error flags as an 8 bit integer.

        Bit 0 = Fan Error, Bit 1 = LED Temp Error, Bit 8 = Any Faults.
        """
        return int(self._transact("C?"))

    def save_settings(self) -> None:
        """Store the current settings to memory."""
        self._transact("S")

    def restore_settings(self) -> None:
        """Restore settings from memory."""
        self._transact("T")

    def reboot(self) -> None:
        """Reboot the unit's processor."""
        self._transact("O4")

    def _transact(self, command: str, name: str | None = None) -> str:
        """Send a command and return its parsed reply value.

        :param command: Command body without the leading `&` or trailing
            carriage return, ex: `"?LT"` or `"I0,500"`.
        :param name: Command name to strip from the reply, needed for set
            commands without a comma, ex: `"E"` for `"E1"`. Inferred if None.
        :return: Value from the reply.
        :raises ColdVisionError: If the send fails, no reply is received, or
            the unit returns a NACK.
        """
        if not self._send_command(command):
            raise ColdVisionError(f"Failed to send command '&{command}'")
        reply = self._read_reply()
        if reply is None:
            raise ColdVisionError(f"No reply received for command '&{command}'")

        if reply.lower().startswith("&n") and not command.lower().startswith("n"):
            raise ColdVisionNack(
                f"Negative acknowledgement for command '&{command}': {reply}"
            )
        return self._parse_value(command, reply, name)

    @staticmethod
    def _parse_value(command: str, reply: str, name: str | None = None) -> str:
        if name is not None:
            prefix = f"&{name}".lower()
        elif "," in command:
            head = command.split(",", 1)[0]
            prefix = f"&{head},".lower()
        else:
            prefix = f"&{command.rstrip('?')}".lower()
        reply_lower = reply.lower()
        if reply_lower.startswith(prefix):
            return reply[len(prefix):]
        return reply

    def _send_command(self, command: str) -> bool:  # pylint: disable=W0221
        """Send a raw legacy command string.

        :param command: Command body without the leading ``&`` or trailing carriage return
        :return: True if the command was sent, False otherwise.
        """
        self._require_connection()
        frame = f"&{command}\r".encode("ascii")
        with self.lock:
            try:
                self.sock.sendall(frame)
            except OSError as exc:
                self.report_error(f"Failed to send command '&{command}': {exc}")
                return False
        self.report_debug(f"Sent: {frame!r}")
        return True

    def _read_reply(self) -> Union[str, None]:
        """Read one reply, up to and including its terminating carriage return."""
        self._require_connection()
        buf = bytearray()
        try:
            while b"\r" not in buf:
                chunk = self.sock.recv(256)
                if not chunk:
                    break
                buf.extend(chunk)
        except OSError as exc:
            self.report_error(f"Failed to read reply: {exc}")
            return None
        if not buf:
            return None
        reply = buf.decode("ascii", errors="replace").strip()
        self.report_debug(f"Received: {reply!r}")
        return reply

    def _require_connection(self) -> None:
        if not self.is_connected() or self.sock is None:
            raise RuntimeError("ColdVision is not connected")

    def __enter__(self) -> "ColdVision":
        return self

    def __exit__(self, *_: object) -> None:
        self.disconnect()
