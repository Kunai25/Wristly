import json
import logging
import math
import time
import random
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, Optional

import serial

# Configure module-level logger
logger = logging.getLogger(__name__)


class BaseSensorSource(ABC):
    """Abstract base class representing a sensor data source."""

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

    @abstractmethod
    def read_packet(self) -> Optional[Dict[str, Any]]:
        """Reads a single sensor data packet.

        Returns:
            A dictionary containing the validated sensor data, or None.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Safely closes the data source connection/resources."""
        pass

    def validate_packet(self, packet: Any) -> bool:
        """Validates that the packet is a dictionary and contains all required keys."""
        if not isinstance(packet, dict):
            logger.warning("Parsed packet is not a dictionary.")
            return False

        for key in self.REQUIRED_KEYS:
            if key not in packet:
                logger.warning(f"Missing required key '{key}' in packet.")
                return False
        return True


class SerialSensorSource(BaseSensorSource):
    """Reads sensor data from a physical serial port using PySerial."""

    def __init__(self, port: str, baudrate: int, timeout: float) -> None:
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

            if self.validate_packet(packet):
                return packet
            return None

        except serial.SerialException as e:
            logger.error(f"Serial communication error: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.debug(f"Failed to decode JSON from serial line: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error reading serial packet: {e}")
            return None

    def close(self) -> None:
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
                logger.info(f"Closed serial port {self.port}.")
            except Exception as e:
                logger.error(f"Error closing serial port {self.port}: {e}")


class SimulationSensorSource(BaseSensorSource):
    """Generates simulated ESP32 sensor packets with realistic wrist movements."""

    def __init__(self) -> None:
        logger.info("Initialized Simulation Sensor Source.")
        self._start_time = time.time()

    def read_packet(self) -> Optional[Dict[str, Any]]:
        # Simulate 20Hz sampling rate delay (50ms)
        time.sleep(0.05)

        t = time.time() - self._start_time

        # Simulate realistic wrist movement using overlapping sine waves and noise
        # Pitch: slow tilt back and forth with occasional quick movements
        pitch = (
            18.0 * math.sin(t * 0.3)
            + 8.0 * math.cos(t * 0.8)
            + random.uniform(-0.5, 0.5)
        )
        # Roll: side-to-side rotation
        roll = (
            22.0 * math.sin(t * 0.25)
            + 5.0 * math.sin(t * 1.2)
            + random.uniform(-0.5, 0.5)
        )
        # Heading: simulated potentiometer rotation (0 to 360 degrees)
        heading = (t * 8.0) % 360.0

        # Convert pitch/roll to radians for approximate gravity vector simulation
        pitch_rad = math.radians(pitch)
        roll_rad = math.radians(roll)

        # Accelerometer values (g)
        ax = -math.sin(pitch_rad) + random.uniform(-0.02, 0.02)
        ay = math.sin(roll_rad) * math.cos(pitch_rad) + random.uniform(-0.02, 0.02)
        az = math.cos(roll_rad) * math.cos(pitch_rad) + random.uniform(-0.02, 0.02)

        # Gyroscope values (deg/s)
        gx = 5.0 * math.cos(t * 0.25) + random.uniform(-0.1, 0.1)
        gy = 5.0 * math.cos(t * 0.3) + random.uniform(-0.1, 0.1)
        gz = random.uniform(-0.2, 0.2)

        packet = {
            "timestamp": int(time.time() * 1000),
            "pitch": round(pitch, 2),
            "roll": round(roll, 2),
            "heading": round(heading, 2),
            "ax": round(ax, 4),
            "ay": round(ay, 4),
            "az": round(az, 4),
            "gx": round(gx, 4),
            "gy": round(gy, 4),
            "gz": round(gz, 4),
        }

        if self.validate_packet(packet):
            return packet
        return None

    def close(self) -> None:
        logger.info("Closed Simulation Sensor Source.")


class SensorReader:
    """Main interface for the dashboard to read sensor data from various sources."""

    def __init__(
        self,
        port: str = "COM3",
        baudrate: int = 115200,
        timeout: float = 1.0,
        source: str = "serial",
    ) -> None:
        self.source_type = source.lower()
        self.source: BaseSensorSource

        if self.source_type == "simulation":
            self.source = SimulationSensorSource()
        else:
            self.source = SerialSensorSource(
                port=port, baudrate=baudrate, timeout=timeout
            )

    def read_packet(self) -> Optional[Dict[str, Any]]:
        """Reads a single packet from the active sensor source."""
        return self.source.read_packet()

    def stream(self) -> Iterator[Dict[str, Any]]:
        """Continuously yields valid sensor data packets from the active source."""
        while True:
            packet = self.read_packet()
            if packet is not None:
                yield packet

    def close(self) -> None:
        """Safely closes the active sensor source."""
        self.source.close()


class SerialSensorReader(SensorReader):
    """Backwards-compatible wrapper for the original SerialSensorReader class.

    Allows app.py to instantiate it without modifications.
    If the port is set to 'simulation' or 'sim', it automatically routes to the simulation source.
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        timeout: float = 1.0,
    ) -> None:
        source = "simulation" if port.lower() in ("simulation", "sim") else "serial"
        super().__init__(port=port, baudrate=baudrate, timeout=timeout, source=source)
