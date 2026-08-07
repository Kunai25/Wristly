import logging
from typing import Any, Dict, List

# Configure module-level logger
logger = logging.getLogger(__name__)


class WristRiskAnalyzer:
    """Analyzes wrist sensor data to calculate ergonomic risk based on posture."""

    # Posture thresholds in degrees
    NEUTRAL_THRESHOLD_DEG: float = 15.0
    MODERATE_THRESHOLD_DEG: float = 30.0

    # Risk Levels
    RISK_LOW: str = "LOW"
    RISK_MEDIUM: str = "MEDIUM"
    RISK_HIGH: str = "HIGH"

    # Required keys in the input sensor data dictionary
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

    def __init__(self) -> None:
        """Initializes the WristRiskAnalyzer."""
        pass

    def analyze(self, sensor_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyzes a single sensor data packet and calculates the ergonomic risk.

        Args:
            sensor_data: A dictionary containing the sensor readings.

        Returns:
            A dictionary containing:
                - "risk_level": "LOW", "MEDIUM", or "HIGH"
                - "risk_score": A numerical score representing risk severity (0.0 to 10.0)
                - "pitch": The analyzed pitch value
                - "roll": The analyzed roll value
                - "warnings": A list of warning messages if deviations are detected
        """
        # Validate input data structure
        if not isinstance(sensor_data, dict):
            logger.error("Input sensor data is not a dictionary.")
            return self._get_error_response(0.0, 0.0, ["Invalid input data format."])

        missing_keys = [key for key in self.REQUIRED_KEYS if key not in sensor_data]
        if missing_keys:
            logger.error(f"Missing required keys in sensor data: {missing_keys}")
            return self._get_error_response(
                0.0, 0.0, [f"Missing keys: {', '.join(missing_keys)}"]
            )

        try:
            pitch: float = float(sensor_data["pitch"])
            roll: float = float(sensor_data["roll"])
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to parse pitch or roll as float: {e}")
            return self._get_error_response(
                0.0, 0.0, ["Invalid numeric values for pitch or roll."]
            )

        abs_pitch = abs(pitch)
        abs_roll = abs(roll)
        max_deviation = max(abs_pitch, abs_roll)

        warnings: List[str] = []
        risk_level: str = self.RISK_LOW

        # Determine risk level and generate warnings
        if abs_pitch > self.MODERATE_THRESHOLD_DEG:
            warnings.append(f"High pitch deviation detected: {pitch:.2f}°")
        elif abs_pitch > self.NEUTRAL_THRESHOLD_DEG:
            warnings.append(f"Moderate pitch deviation detected: {pitch:.2f}°")

        if abs_roll > self.MODERATE_THRESHOLD_DEG:
            warnings.append(f"High roll deviation detected: {roll:.2f}°")
        elif abs_roll > self.NEUTRAL_THRESHOLD_DEG:
            warnings.append(f"Moderate roll deviation detected: {roll:.2f}°")

        if max_deviation > self.MODERATE_THRESHOLD_DEG:
            risk_level = self.RISK_HIGH
        elif max_deviation > self.NEUTRAL_THRESHOLD_DEG:
            risk_level = self.RISK_MEDIUM
        else:
            risk_level = self.RISK_LOW

        # Calculate a normalized risk score from 0.0 to 10.0
        risk_score = self._calculate_risk_score(max_deviation)

        return {
            "risk_level": risk_level,
            "risk_score": round(risk_score, 2),
            "pitch": pitch,
            "roll": roll,
            "warnings": warnings,
        }

    def _calculate_risk_score(self, max_deviation: float) -> float:
        """Calculates a continuous risk score from 0.0 to 10.0 based on maximum deviation.

        - 0.0 to 3.0: Low risk (0 to 15 degrees)
        - 3.0 to 7.0: Medium risk (15 to 30 degrees)
        - 7.0 to 10.0: High risk (30 to 90+ degrees)
        """
        if max_deviation <= self.NEUTRAL_THRESHOLD_DEG:
            # Map [0, 15] to [0.0, 3.0]
            return (max_deviation / self.NEUTRAL_THRESHOLD_DEG) * 3.0
        elif max_deviation <= self.MODERATE_THRESHOLD_DEG:
            # Map (15, 30] to (3.0, 7.0]
            range_fraction = (max_deviation - self.NEUTRAL_THRESHOLD_DEG) / (
                self.MODERATE_THRESHOLD_DEG - self.NEUTRAL_THRESHOLD_DEG
            )
            return 3.0 + (range_fraction * 4.0)
        else:
            # Map (30, 90] to (7.0, 10.0]
            excess = max_deviation - self.MODERATE_THRESHOLD_DEG
            # Cap the maximum expected deviation at 90 degrees for scaling
            max_excess = 60.0
            range_fraction = min(excess / max_excess, 1.0)
            return 7.0 + (range_fraction * 3.0)

    def _get_error_response(
        self, pitch: float, roll: float, warnings: List[str]
    ) -> Dict[str, Any]:
        """Helper to return a safe fallback response in case of errors."""
        return {
            "risk_level": self.RISK_HIGH,
            "risk_score": 10.0,
            "pitch": pitch,
            "roll": roll,
            "warnings": warnings,
        }
