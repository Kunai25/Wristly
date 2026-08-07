import json
import logging
import socket
from typing import Any, Dict, Optional

from dashboard.serial_reader import BaseSensorSource

# Configure module-level logger
logger = logging.getLogger(__name__)


class WokwiSensorSource(BaseSensorSource):
    """Reads sensor data from a Wokwi simulation endpoint.
    
    Wokwi simulations typically stream serial output over a TCP socket or a WebSocket
    bridge (e.g., using wokwi-server or a custom gateway). This class connects to
    the specified endpoint, receives newline-delimited JSON packets, and validates them.
    """

    def __init__(self, host: str = "localhost", port: int = 4000, timeout: float = 1.0) -> None:
        """Initializes the Wokwi sensor source.

        Args:
            host: The hostname or IP address of the Wokwi gateway/bridge.
            port: The port number of the Wokwi gateway/bridge.
            timeout: Connection and read timeout in seconds.
        """
        self.host = host
        self.port = port
        self.timeout = timeout
        self._socket: Optional[socket.socket] = None
        self._buffer = ""

        logger.info(f"Initializing Wokwi Sensor Source targeting {self.host}:{self.port}")
        
        # TODO: If your Wokwi setup uses WebSockets instead of a raw TCP socket,
        # replace this socket initialization with a WebSocket client connection
        # (e.g., using the `websocket-client` library).
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(self.timeout)
            self._socket.connect((self.host, self.port))
            logger.info(f"Successfully connected to Wokwi simulation at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to connect to Wokwi simulation at {self.host}:{self.port}: {e}")
            self._socket = None
            # Raise so the dashboard's connection handler can surface a real error to the
            # user instead of silently falling through — read_packet() would otherwise
            # return None forever with no socket, and the stream() loop has no delay on
            # None results, which turns into a tight, CPU-pegging busy loop.
            raise ConnectionError(
                f"Could not reach the Wokwi bridge at {self.host}:{self.port}. "
                f"Is the Wokwi simulation / serial bridge running?"
            ) from e

    def read_packet(self) -> Optional[Dict[str, Any]]:
        """Reads and parses a single newline-delimited JSON packet from the Wokwi connection."""
        if not self._socket:
            logger.warning("Wokwi socket connection is not established.")
            return None

        try:
            # Read data until we find a newline character
            while "\n" not in self._buffer:
                data = self._socket.recv(1024)
                if not data:
                    logger.warning("Wokwi connection closed by remote host.")
                    return None
                self._buffer += data.decode("utf-8", errors="ignore")

            # Extract the first complete line
            line, self._buffer = self._buffer.split("\n", 1)
            line = line.strip()
            if not line:
                return None

            # Parse JSON
            packet: Dict[str, Any] = json.loads(line)

            # Validate using the base class validation logic
            if self.validate_packet(packet):
                return packet
            return None

        except socket.timeout:
            logger.debug("Wokwi socket read timed out.")
            return None
        except json.JSONDecodeError as e:
            logger.debug(f"Failed to decode JSON from Wokwi stream: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading Wokwi packet: {e}")
            return None

    def close(self) -> None:
        """Safely closes the Wokwi connection."""
        if self._socket:
            try:
                self._socket.close()
                logger.info("Closed Wokwi simulation connection.")
            except Exception as e:
                logger.error(f"Error closing Wokwi socket: {e}")
            finally:
                self._socket = None
