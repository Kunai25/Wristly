# Wristly

Reduce the risk to your wrist — a wrist-worn ergonomic monitor that tracks posture in real time, alerts on sustained strain, and gives AI-generated recommendations.

Built solo for **NGN Hacks 2026** (48-hour online hackathon).

## What this is

- **Firmware:** ESP32 + MPU6050 IMU, simulated end-to-end in [Wokwi](https://wokwi.com) (no physical hardware required to run this)
- **Dashboard:** Python + Streamlit — live risk gauge, motion history, AI recommendations
- **AI:** [Featherless AI](https://featherless.ai) for ergonomic recommendations
- **Housing:** 3D-modeled in SelfCAD (see presentation deck for renders)

## Running it

### 1. Firmware (Wokwi simulation)

Requires [Arduino CLI](https://arduino.github.io/arduino-cli/) with the `esp32:esp32` core installed, and the [Wokwi VS Code extension](https://marketplace.visualstudio.com/items?itemName=wokwi.wokwi-vscode) (or `wokwi-cli`).

Compile the firmware — the `--output-dir` flag matters, Wokwi loads the prebuilt binary rather than compiling from source:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32 firmware --output-dir firmware/build
```

Then open this folder in VS Code and start the Wokwi simulation (`wokwi.toml` is already configured to point at `firmware/build/firmware.ino.bin`). Once running, it boots, calibrates, and streams JSON telemetry over an RFC2217 bridge on `localhost:4000`.

### 2. Dashboard

```bash
pip install -r requirements.txt
```

Set your Featherless API key as an environment variable before launching:

```bash
# macOS/Linux
export FEATHERLESS_API_KEY="your_key_here"

# Windows PowerShell
$env:FEATHERLESS_API_KEY = "your_key_here"
```

Then run:

```bash
streamlit run dashboard/app.py
```

In the sidebar, choose **Simulation Mode → wokwi** as the sensor source and hit **Start** — the dashboard connects to the running Wokwi sim and starts rendering live risk data.

## Project structure

```
Wristly/
├── firmware/        ESP32 firmware, Wokwi config
├── dashboard/        Streamlit app, risk analytics, AI recommendations
├── requirements.txt
└── README.md
```

## Notes

- No physical hardware is needed — the IMU is fully simulated in Wokwi.
- This is presented as ergonomic risk monitoring / early-warning, not a diagnostic or medical device.
