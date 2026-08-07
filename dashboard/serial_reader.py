import json
import logging
from typing import Any, Dict, Iterator, Optional

import serial

# Configure module-level logger
logger = logging.getLogger(__name__)


class SerialSensorReader:
    """A production-quality reader for parsing newline-delimited JSON data

    from an ESP32 over a serial connection.
    """

    # Default connection parameters
    DEFAULT_BAUDRATE: int = 115200
    DEFAULT_TIMEOUT_SECONDS: float = 1.0

    # Required keys in the incoming JSON packet
    REQUIRED_KEYS: tuple = (
        "timestamp",
        "pitch",
        "roll",
        "heading",
        "ax",
        "ay",
        "az",
        "gx",
        "gy",
        "gz",
    )

    def __init__(
        self,
        port: str,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initializes the serial connection.

        Args:
            port: The serial port identifier (e.g., 'COM3' or '/dev/ttyUSB0').
            baudrate: The communication speed. Defaults to 115200.
            timeout: Read timeout in seconds. Defaults to 1.0.

        Raises:
            serial.SerialException: If the serial port cannot be opened.
        """
        self.port: str = port
        self.baudrate: int = baudrate
        self.timeout: float = timeout
        self._serial: Optional[serial.Serial] = None

        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=self.timeout,
            )
            logger.info(
                f"Successfully opened serial port {self.port} at {self.baudrate} baud."
            )
        except serial.SerialException as e:
            logger.error(f"Failed to open serial port {self.port}: {e}")
            raise

    def read_packet(self) -> Optional[Dict[str, Any]]:
        """Reads a single line from the serial port, decodes it, and parses it as JSON.

        Returns:
            A dictionary containing the validated sensor data, or None if
            reading, decoding, parsing, or validation fails.
        """
        if not self._serial or not self._serial.is_open:
            logger.warning("Serial port is not open.")
            return None

        try:
            raw_line: bytes = self._serial.readline()
            if not raw_line:
                return None

            # Decode ignoring strict UTF-8 errors
            decoded_line: str = raw_line.decode("utf-8", errors="ignore").strip()
            if not decoded_line:
                return None

            # Parse JSON
            packet: Dict[str, Any] = json.loads(decoded_line)

            # Validate required keys
            if not isinstance(packet, dict):
                logger.warning("Parsed JSON is not a dictionary.")
                return None

            for key in self.REQUIRED_KEYS:
                if key not in packet:
                    logger.warning(f"Missing required key '{key}' in packet.")
                    return None

            return packet

        except serial.SerialException as e:
            logger.error(f"Serial communication error: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.debug(f"Failed to decode JSON from serial line: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading serial packet: {e}")
            return None

    def stream(self) -> Iterator[Dict[str, Any]]:
        """Continuously yields valid sensor data packets from the serial stream.

        Yields:
            Validated dictionaries containing sensor data.
        """
        while self._serial and self._serial.is_open:
            packet = self.read_packet()
            if packet is not None:
                yield packet

    def close(self) -> None:
        """Safely closes the serial port connection."""
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
                logger.info(f"Closed serial port {self.port}.")
            except Exception as e:
                logger.error(f"Error closing serial port {self.port}: {e}")
