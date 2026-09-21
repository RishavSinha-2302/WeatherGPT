# WeatherGPT 🌦️🌾

> **Zero-Cost Conversational AI routing user queries to real-time Numerical Weather Prediction (NWP), Agricultural Advisories, and WMO WIS 2.0 Hazard Polygons with Multilingual Voice (Hindi, Marathi, English).**

Built using a strictly ₹0 budget, high-performance stack:
- **Zero Node/npm Dependency**: The full responsive React 18 + Tailwind CSS UI is served directly through FastAPI via CDN.
- **Python Backend**: Fast asynchronous FastAPI server managed via `uv`.
- **AI Router**: OpenAI-compatible LLM router using Function / Tool Calling (supports OpenAI, OpenRouter, Groq, Ollama, DeepSeek, vLLM, etc.).
- **NWP Engine**: Open-Meteo API serving free GFS/ECMWF numerical weather models and 7-day agricultural soil moisture / precipitation forecasts.
- **Spatial Database**: Supabase PostgreSQL with PostGIS extension for polygon warning intersection.
- **Alert Ingestion**: `paho-mqtt` background worker listening to WMO WIS 2.0 real-time hazard broker.
- **Zero-Cost Voice**: Native HTML5 Web Speech API for speech-to-text (STT) and text-to-speech (TTS) in regional languages (`hi-IN`, `mr-IN`, `en-IN`).

---

## 🏛️ System Architecture

```
                                  +---------------------------------------+
                                  |     Farmer / Citizen Mobile Device    |
                                  |    (WhatsApp-Style Voice Interface)   |
                                  +-------------------+-------------------+
                                                      |
                                     HTML5 Audio STT / TTS & GPS Lat/Lon
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |          FastAPI Backend Server       |
                                  |         (POST /api/chat, static)      |
                                  +-------------------+-------------------+
                                                      |
                                     Function Calling & Intent Routing
                                                      |
                                                      v
                                  +---------------------------------------+
                                  |     OpenAI-Compatible LLM Router      |
                                  |       (Function / Tool Calling)       |
                                  +----+--------------------+--------+----+
                                       |                    |        |
             +-------------------------+                    |        +-------------------------+
             |                                              |                                  |
             v                                              v                                  v
+--------------------------+                   +--------------------------+       +--------------------------+
|  `get_current_weather`   |                   |`get_agricultural_forecast|       | `check_location_alerts`  |
|  Open-Meteo Current NWP  |                   |  7-Day Soil Moisture,    |       |  Supabase PostGIS Spatial|
|  Temp, Wind, Conditions  |                   |  Rain & Wind Advisories  |       |  Hazard Warning Polygons |
+--------------------------+                   +--------------------------+       +--------------------------+
                                                                                               ^
                                                                                               |
                                                                                  +------------+-------------+
                                                                                  |  WIS 2.0 MQTT Listener   |
                                                                                  |  (`mqtt_listener.py`)    |
                                                                                  +--------------------------+
```

---

## 🚀 Quick Start Guide (Using `uv`)

This project uses [`uv`](https://docs.astral.sh/uv/) for fast, zero-configuration Python environment and package management without requiring Node.js or npm.

### 1. Install `uv` (if not already installed)
- **Windows (PowerShell)**:
  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```
- **macOS / Linux**:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Or via pip**:
  ```bash
  pip install uv
  ```

### 2. Clone the Repository
```bash
git clone https://github.com/RishavSinha-2302/WeatherGPT.git
cd WeatherGPT
```

### 3. Install Project Dependencies
Sync all dependencies into the virtual environment:
```bash
uv sync
```

### 4. Launch the Application
Start the FastAPI server:
```bash
uv run main.py
```
*(Alternatively: `uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000`)*

Open your browser at **[http://localhost:8000](http://localhost:8000)**.

---

## 🎙️ Key Capabilities & Regional Voice

- **Bilingual & Multilingual Speech**:
  - Toggle between **English**, **हिन्दी (Hindi)**, and **मराठी (Marathi)**.
  - Press the **Microphone** button to speak questions like *"आज पाऊस पडेल का?"* or *"क्या आज कीटनाशक का छिड़काव कर सकते हैं?"*.
  - Click **Speak** on any assistant response to hear the advisory read aloud with native Devanagari pronunciation.
- **Agricultural Decision Support**:
  - Surface & root-zone soil moisture interpretation ($m^3/m^3$).
  - Precipitation probability threshold checks (prevents wasted fertilizer/pesticide sprays).
  - Wind speed warnings for foliar spraying.
- **Spatial Hazard Alert Verification**:
  - Live GPS coordinate detection with `navigator.geolocation`.
  - Stored polygon intersection using PostGIS `ST_Contains` matching WMO WIS 2.0 alerts.
  - Interactive weather station selector for Pune, Nashik, Nagpur, Kolhapur, Mumbai, and Delhi NCR.

---

## 📁 Repository Structure

| File | Description |
|---|---|
| `main.py` | FastAPI server hosting `/api/chat`, `/api/weather/quick`, `/api/health`, and static files |
| `agent.py` | OpenAI-compatible agent router with Tool/Function Calling and multilingual synthesis |
| `tools.py` | Async tools for Open-Meteo current NWP, 7-day agricultural forecast, and PostGIS alerts |
| `mqtt_listener.py` | WMO WIS 2.0 MQTT worker ingesting hazard bounding boxes into Supabase PostGIS |
| `schema.sql` | SQL initialization script for Supabase with PostGIS spatial geometry and RPC functions |
| `static/index.html` | Modern HTML5 PWA host page with Tailwind CSS and Lucide Icons via CDN |
| `static/app.jsx` | WhatsApp-style React chat app with HTML5 Web Speech STT/TTS and Geolocation |
| `pyproject.toml` | UV project specification with Python 3.11+ dependencies |

---
