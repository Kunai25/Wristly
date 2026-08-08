import json
import logging
from typing import Any, Dict, Optional

import serial

from dashboard.serial_reader import BaseSensorSource

# Configure module-level logger
logger = logging.getLogger(__name__)


class WokwiSensorSource(BaseSensorSource):
    """Reads sensor data from a live Wokwi simulation via its RFC2217 serial bridge.

    "Wokwi for VS Code" can expose the simulated ESP32's serial port over TCP by
    adding `rfc2217ServerPort = 4000` to the [wokwi] section of wokwi.toml. That is
    NOT a plain newline-delimited TCP stream — it's the RFC2217 protocol (remote
    serial port control, layered with Telnet option negotiation), so a raw socket
    read here would occasionally pick up protocol bytes mixed into the data and
    corrupt or drop JSON lines. PySerial already understands RFC2217, so we let it
    handle the protocol and treat the connection exactly like a normal serial port.
    """

    def __init__(self, host: str = "localhost", port: int = 4000, timeout: float = 1.0,
                 baudrate: int = 115200) -> None:
        """Initializes the Wokwi sensor source.

        Args:
            host: The hostname of the machine running "Wokwi for VS Code" (usually localhost).
            port: The rfc2217ServerPort configured in firmware/wokwi.toml (default 4000).
            timeout: Read timeout in seconds.
            baudrate: Must match Serial.begin(...) in firmware.ino (115200).
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self.baudrate = baudrate
        self._serial: Optional[serial.Serial] = None

        url = f"rfc2217://{self.host}:{self.port}"
        logger.info(f"Connecting to Wokwi RFC2217 bridge at {url} (baud={self.baudrate})")

        try:
            self._serial = serial.serial_for_url(url, baudrate=self.baudrate, timeout=self.timeout)
            logger.info(f"Successfully connected to Wokwi simulation at {url}")
        except Exception as e:
            logger.error(f"Failed to connect to Wokwi simulation at {url}: {e}")
            self._serial = None
            # Raise so the dashboard's connection handler can surface a real error to
            # the user (see app.py's try/except around SerialSensorReader). Silently
            # continuing here would leave read_packet() returning None forever with
            # nothing telling the user *why* — and previously turned into a
            # CPU-pegging busy loop in serial_reader.py's stream() generator.
            raise ConnectionError(
                f"Could not reach the Wokwi RFC2217 bridge at {url}. "
                f"Is the Wokwi for VS Code simulation running, with "
                f"rfc2217ServerPort = {self.port} set in firmware/wokwi.toml?"
            ) from e

    def read_packet(self) -> Optional[Dict[str, Any]]:
        """Reads and parses a single newline-delimited JSON packet from the bridge."""
        if not self._serial or not self._serial.is_open:
            logger.warning("Wokwi RFC2217 connection is not open.")
            return None

        try:
            raw_line: bytes = self._serial.readline()
            if not raw_line:
                return None

            decoded_line: str = raw_line.decode("utf-8", errors="ignore").strip()
            if not decoded_line:
                return None

            packet: Dict[str, Any] = json.loads(decoded_line)

            if self.validate_packet(packet):
                return packet
            return None

        except serial.SerialException as e:
            logger.error(f"Wokwi serial communication error: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.debug(f"Failed to decode JSON from Wokwi stream: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading Wokwi packet: {e}")
            return None

    def close(self) -> None:
        """Safely closes the Wokwi RFC2217 connection."""
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
                logger.info("Closed Wokwi RFC2217 connection.")
            except Exception as e:
                logger.error(f"Error closing Wokwi connection: {e}")
            finally:
                self._serial = None
