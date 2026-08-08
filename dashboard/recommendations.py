import os
import logging
import requests
from typing import Any, Dict, List

# Configure module-level logger
logger = logging.getLogger(__name__)

class ErgonomicRecommendationEngine:
    """Generates personalized ergonomic recommendations using Featherless AI
    based on wrist risk analysis data.
    """

    # Featherless AI API Constants
    DEFAULT_API_ENDPOINT: str = "https://api.featherless.ai/v1/chat/completions"
    DEFAULT_MODEL: str = "meta-llama/Meta-Llama-3-8B-Instruct"
    DEFAULT_TIMEOUT_SECONDS: float = 60.0

    def __init__(self, api_key: str = "") -> None:
        """Initializes the recommendation engine."""
        self.api_key = api_key or os.environ.get("FEATHERLESS_API_KEY", "")
        
        # Ensures the endpoint always correctly hits the chat/completions route
        base_endpoint = os.environ.get("FEATHERLESS_API_ENDPOINT", self.DEFAULT_API_ENDPOINT)
        if base_endpoint.endswith("/v1") or base_endpoint.endswith("/v1/"):
            self.api_endpoint = base_endpoint.rstrip("/") + "/chat/completions"
        else:
            self.api_endpoint = base_endpoint
            
        self.model = os.environ.get("FEATHERLESS_MODEL", self.DEFAULT_MODEL)

    def generate_recommendation(self, risk_data: Dict[str, Any]) -> str:
        """Validates risk data, constructs a prompt, and calls Featherless AI."""
        
        # 1. Validate input data structure
        if not isinstance(risk_data, dict):
            logger.error("Input risk_data is not a dictionary.")
            return "Error: Invalid risk data format provided."

        required_keys = ["risk_level", "risk_score", "pitch", "roll", "warnings"]
        missing_keys = [key for key in required_keys if key not in risk_data]
        if missing_keys:
            logger.error(f"Missing required keys in risk data: {missing_keys}")
            return f"Error: Missing required risk metrics: {', '.join(missing_keys)}."

        # 2. Check API Key
        if not self.api_key:
            logger.error("Featherless API key is missing. Please set FEATHERLESS_API_KEY.")
            return "Error: Featherless API key is not configured. Please set the FEATHERLESS_API_KEY environment variable."

        # 3. Process Data and Call API (Wrapped safely to prevent hardware crashes)
        try:
            # Extract values safely
            risk_level: str = str(risk_data["risk_level"])
            risk_score: float = float(risk_data["risk_score"])
            pitch: float = float(risk_data["pitch"])
            roll: float = float(risk_data["roll"])
            warnings: List[str] = risk_data["warnings"]

            # Construct the prompt
            warnings_text = "\n".join([f"- {w}" for w in warnings]) if warnings else "- None"
            
            prompt = (
                f"You are an expert ergonomic assistant. Analyze the following wrist sensor metrics "
                f"and provide brief, actionable, and personalized ergonomic recommendations to prevent "
                f"Repetitive Strain Injury (RSI) or Carpal Tunnel Syndrome.\n\n"
                f"### Wrist Sensor Metrics:\n"
                f"- Risk Level: {risk_level}\n"
                f"- Risk Score: {risk_score}/10.0\n"
                f"- Pitch Angle: {pitch:.2f}°\n"
                f"- Roll Angle: {roll:.2f}°\n"
                f"- Active Warnings:\n{warnings_text}\n\n"
                f"### Instructions:\n"
                f"Provide 2-3 specific, concise, and practical recommendations.\n"
                f"CRITICAL FORMATTING RULE: Write each recommendation on a single continuous line. Format exactly like this: '1. **Title:** Description'. Do not put line breaks between the number and the title.\n"
                f"Keep the tone professional, encouraging, and direct."
            )

            # Call Featherless AI API
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful, professional ergonomic coach specializing in wrist health and posture.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.7,
            }

            logger.info(f"Sending request to Featherless AI using model: {self.model}")
            
            response = requests.post(
                self.api_endpoint,
                headers=headers,
                json=payload,
                timeout=self.DEFAULT_TIMEOUT_SECONDS,
            )

            if response.status_code == 200:
                response_json = response.json()
                choices = response_json.get("choices", [])
                if choices:
                    recommendation = choices[0].get("message", {}).get("content", "").strip()
                    if recommendation:
                        return recommendation
                logger.error("Featherless AI response did not contain expected text choices.")
                return "Error: Received empty recommendation from the AI service."
            else:
                logger.error(f"Featherless AI API returned status code {response.status_code}: {response.text}")
                return f"Error: AI service returned status code {response.status_code}."

        except ValueError as ve:
            logger.error(f"Hardware data parsing error: {ve}")
            return "Error: Received corrupted sensor data from the glove."
        except requests.exceptions.Timeout:
            logger.error("Timeout occurred while connecting to Featherless AI.")
            return "Error: Connection to the AI service timed out."
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error occurred while calling Featherless AI: {e}")
            return "Error: Failed to connect to the AI service."
        except Exception as e:
            logger.error(f"Unexpected error during recommendation generation: {e}")
            return "Error: An unexpected error occurred while generating recommendations."