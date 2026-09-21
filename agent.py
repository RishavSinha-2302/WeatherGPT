"""
WeatherGPT Agent Module
Implements OpenAI-compatible chat completions router with Function/Tool Calling for NWP weather data,
agricultural advisories, and spatial alert verification.
Supports any OpenAI-compatible provider (OpenAI, OpenRouter, Groq, Ollama, DeepSeek, vLLM, etc.)
with model and endpoint configured via .env, alongside intelligent multi-lingual voice synthesis routing.
"""

import os
import json
import logging
import asyncio
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from openai import AsyncOpenAI

from tools import get_current_weather, get_agricultural_forecast, check_location_alerts

load_dotenv()
logger = logging.getLogger("weathergpt.agent")

# Sync wrappers for tool execution
def tool_get_current_weather(lat: float, lon: float) -> dict:
    """Fetch current real-time weather (temperature, wind speed, weather code) from Open-Meteo NWP for coordinates lat, lon."""
    import httpx
    resp = httpx.get(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true", timeout=10.0)
    data = resp.json().get("current_weather", {})
    return {
        "latitude": lat,
        "longitude": lon,
        "temperature": data.get("temperature"),
        "wind_speed": data.get("windspeed"),
        "wind_direction": data.get("winddirection"),
        "weather_code": data.get("weathercode"),
        "is_day": data.get("is_day")
    }

def tool_get_agricultural_forecast(lat: float, lon: float) -> dict:
    """Fetch 7-day agricultural forecast (soil moisture at 0-1cm and 1-3cm depth, precipitation probability, daily rainfall, wind speed) from Open-Meteo for coordinates lat, lon."""
    import httpx
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        "&daily=precipitation_probability_max,precipitation_sum,wind_speed_10m_max,temperature_2m_max,temperature_2m_min"
        "&hourly=soil_moisture_0_to_1cm,soil_moisture_1_to_3cm,relative_humidity_2m"
        "&timezone=auto&forecast_days=7"
    )
    resp = httpx.get(url, timeout=12.0)
    data = resp.json()
    daily = data.get("daily", {})
    hourly = data.get("hourly", {})
    soil_0_1 = hourly.get("soil_moisture_0_to_1cm", [])
    recent = soil_0_1[:24] if soil_0_1 else []
    avg_soil = round(sum(recent)/len(recent), 3) if recent else 0.25
    return {
        "latitude": lat,
        "longitude": lon,
        "soil_moisture_surface_m3_m3": avg_soil,
        "next_7_days_dates": daily.get("time", [])[:7],
        "precipitation_probability_pct": daily.get("precipitation_probability_max", [])[:7],
        "precipitation_sum_mm": daily.get("precipitation_sum", [])[:7],
        "max_wind_speed_kmh": daily.get("wind_speed_10m_max", [])[:7],
        "max_temp_c": daily.get("temperature_2m_max", [])[:7],
        "min_temp_c": daily.get("temperature_2m_min", [])[:7]
    }

def tool_check_location_alerts(lat: float, lon: float) -> dict:
    """Fetch active severe weather hazard warnings from WeatherAPI for coordinates lat, lon."""
    import httpx
    load_dotenv(override=True)
    api_key = os.getenv("WEATHERAPI_API_KEY", "").strip()
    if not api_key:
        logger.warning("WEATHERAPI_API_KEY not configured in .env")
        return {"latitude": lat, "longitude": lon, "active_alerts_count": 0, "alerts": [], "status": "no_key"}

    url = f"https://api.weatherapi.com/v1/alerts.json?key={api_key}&q={lat},{lon}"
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        raw_alerts = data.get("alerts", {}).get("alert", [])
        alerts = []
        for item in raw_alerts:
            desc = item.get("headline") or item.get("event") or item.get("desc") or "Weather Alert"
            if item.get("instruction"):
                desc = f"{desc}. Instruction: {item.get('instruction')}"
            alerts.append({
                "severity": (item.get("severity") or "warning").lower(),
                "event": item.get("event", ""),
                "headline": item.get("headline", ""),
                "description": desc,
                "active_until": item.get("expires") or item.get("effective") or "Ongoing",
                "instruction": item.get("instruction", ""),
                "source": "WeatherAPI Alerts"
            })
        return {
            "latitude": lat,
            "longitude": lon,
            "location": data.get("location", {}).get("name", ""),
            "region": data.get("location", {}).get("region", ""),
            "active_alerts_count": len(alerts),
            "alerts": alerts,
            "status": "success"
        }
    except Exception as e:
        logger.warning(f"Failed to fetch alerts from WeatherAPI: {e}")
        return {
            "latitude": lat,
            "longitude": lon,
            "active_alerts_count": 0,
            "alerts": [],
            "status": "failed",
            "error": str(e)
        }

TOOL_REGISTRY = {
    "get_current_weather": tool_get_current_weather,
    "tool_get_current_weather": tool_get_current_weather,
    "get_agricultural_forecast": tool_get_agricultural_forecast,
    "tool_get_agricultural_forecast": tool_get_agricultural_forecast,
    "check_location_alerts": tool_check_location_alerts,
    "tool_check_location_alerts": tool_check_location_alerts,
}

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_weather",
            "description": "Fetch current real-time weather (temperature, wind speed, weather code) from Open-Meteo NWP for coordinates lat, lon.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": "Latitude coordinate of target location"
                    },
                    "lon": {
                        "type": "number",
                        "description": "Longitude coordinate of target location"
                    }
                },
                "required": ["lat", "lon"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_agricultural_forecast",
            "description": "Fetch 7-day agricultural forecast (soil moisture, precipitation probability, daily rainfall, wind speed, temperatures) from Open-Meteo for coordinates lat, lon.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": "Latitude coordinate of target location"
                    },
                    "lon": {
                        "type": "number",
                        "description": "Longitude coordinate of target location"
                    }
                },
                "required": ["lat", "lon"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_location_alerts",
            "description": "Fetch real-time active severe weather hazard alerts and warning advisories from WeatherAPI for coordinates lat, lon.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": "Latitude coordinate of target location"
                    },
                    "lon": {
                        "type": "number",
                        "description": "Longitude coordinate of target location"
                    }
                },
                "required": ["lat", "lon"]
            }
        }
    }
]

SYSTEM_PROMPT = """You are WeatherGPT, an advanced Conversational AI routing assistant for numerical weather prediction (NWP) and agricultural advisories.
You serve farmers, agricultural workers, and citizens across India in regional languages (Hindi, Marathi, English).

You have access to 3 real-time tools:
1. `get_current_weather(lat, lon)`: Real-time current temperature, wind speed, weather code.
2. `get_agricultural_forecast(lat, lon)`: 7-day soil moisture, precipitation probability, rainfall, wind speeds, and temperatures.
3. `check_location_alerts(lat, lon)`: Real-time severe weather hazard alerts and warnings from WeatherAPI.

IMPORTANT INSTRUCTIONS:
- ALWAYS check the user's provided GPS coordinates (lat, lon).
- Use the tools whenever the user asks about current conditions, upcoming rain, crop advisories, soil moisture, spraying conditions, or severe weather alerts.
- Respond in the user's requested language.
  - If language is 'hi' (Hindi), respond in natural, friendly Hindi (Devanagari script).
  - If language is 'mr' (Marathi), respond in natural, friendly Marathi (Devanagari script).
  - If language is 'en' (English), respond in clear, accessible English.
- Agricultural guidance: Translate numerical data into actionable farm wisdom (e.g., if rain probability is >60%, advise postponing pesticide spray or chemical fertilizer application; if wind speed >25 km/h, caution against foliar spray).
- Keep responses conversational, concise, and structured so they can be easily spoken out loud using Text-to-Speech.
"""


class WeatherAgent:
    def __init__(self):
        self.client: Optional[AsyncOpenAI] = None
        self.active_key: Optional[str] = None
        self.active_base_url: Optional[str] = None
        self.model_name: str = "gemini-3.1-flash-lite"
        self._init_client()

    def _init_client(self):
        load_dotenv(override=True)
        key = (os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY", "")).strip()
        base_url = (os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL", "")).strip() or None
        self.model_name = (os.getenv("OPENAI_MODEL") or os.getenv("MODEL_NAME") or "gpt-4o-mini").strip()

        if key:
            try:
                self.client = AsyncOpenAI(
                    api_key=key,
                    base_url=base_url
                )
                self.active_key = key
                self.active_base_url = base_url
                logger.info(f"OpenAI-compatible client initialized (model: {self.model_name}, base_url: {base_url or 'default'}).")
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI-compatible client: {e}")
                self.client = None
                self.active_key = None
                self.active_base_url = None
        else:
            self.client = None
            self.active_key = None
            self.active_base_url = None

    async def chat(self, user_message: str, lat: float, lon: float, language: str = "en") -> Dict[str, Any]:
        """
        Routes user query through OpenAI-compatible Chat Completions with Tool Calling.
        Falls back seamlessly to rule-based routing if API key is missing, invalid, or error occurs.
        """
        # Dynamically check for new or updated configuration in .env
        load_dotenv(override=True)
        current_env_key = (os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY", "")).strip()
        current_base_url = (os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL", "")).strip() or None
        current_model = (os.getenv("OPENAI_MODEL") or os.getenv("MODEL_NAME") or "gpt-4o-mini").strip()

        if (current_env_key != (self.active_key or "") or
            current_base_url != self.active_base_url or
            current_model != self.model_name):
            self._init_client()

        tools_called = []

        if self.client:
            try:
                messages = [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"User Location: Latitude {lat}, Longitude {lon}\n"
                            f"Requested Response Language: {language} (en=English, hi=Hindi, mr=Marathi)\n"
                            f"User Query: {user_message}"
                        )
                    }
                ]

                response = await self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    tools=OPENAI_TOOLS,
                    tool_choice="auto",
                    temperature=0.2
                )

                response_message = response.choices[0].message
                tool_calls = getattr(response_message, "tool_calls", None)

                if tool_calls:
                    messages.append(response_message)
                    for tool_call in tool_calls:
                        fn_name = tool_call.function.name
                        try:
                            fn_args = json.loads(tool_call.function.arguments or "{}")
                        except Exception:
                            fn_args = {}

                        tool_fn = TOOL_REGISTRY.get(fn_name)
                        if tool_fn:
                            try:
                                if asyncio.iscoroutinefunction(tool_fn):
                                    tool_res = await tool_fn(**fn_args)
                                else:
                                    tool_res = tool_fn(**fn_args)
                            except Exception as te:
                                logger.warning(f"Error executing tool {fn_name}: {te}")
                                tool_res = {"error": str(te)}
                        else:
                            tool_res = {"error": f"Tool '{fn_name}' not found."}

                        tools_called.append({
                            "tool": fn_name,
                            "args": fn_args,
                            "result": tool_res
                        })

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(tool_res)
                        })

                    # Second call to synthesize tool results
                    final_response = await self.client.chat.completions.create(
                        model=self.model_name,
                        messages=messages,
                        temperature=0.2
                    )
                    reply_text = final_response.choices[0].message.content or "Here is the weather advisory."
                else:
                    reply_text = response_message.content or "Here is the weather advisory."

                return {
                    "reply": reply_text,
                    "tools_called": tools_called,
                    "model": self.model_name,
                    "status": "success"
                }
            except Exception as e:
                logger.warning(f"LLM API encountered an error ({e}). Seamlessly falling back to standalone NWP router.")

        # Standalone NWP router fallback (runs automatically if key is missing or invalid)
        return await self._fallback_route(user_message, lat, lon, language)

    async def _fallback_route(self, message: str, lat: float, lon: float, language: str) -> Dict[str, Any]:
        """Deterministic NWP routing engine when LLM API is not configured or unavailable."""
        msg_lower = message.lower()
        tools_called = []
        
        need_alerts = any(w in msg_lower for w in ["alert", "warning", "danger", "storm", "cyclone", "safet", "खतरा", "इशारा", "वादळ", "सावधान", "चेतावनी"])
        need_agri = any(w in msg_lower for w in ["soil", "crop", "farm", "sow", "spray", "moisture", "rain", "precip", "harvest", "शेती", "पीक", "माती", "पाऊस", "पेरणी", "फवारणी", "बारिश", "फसल", "सिंचाई"])
        need_current = not (need_alerts or need_agri) or any(w in msg_lower for w in ["now", "today", "temperature", "temp", "current", "wind", "आज", "तापमान", "हवामान", "मौसम"])

        current_data = None
        agri_data = None
        alert_data = None

        if need_current or (not need_agri and not need_alerts):
            current_data = await get_current_weather(lat, lon)
            tools_called.append({"tool": "get_current_weather", "args": {"lat": lat, "lon": lon}, "result": current_data})

        if need_agri or "rain" in msg_lower or "पाऊस" in msg_lower or "बारिश" in msg_lower:
            agri_data = await get_agricultural_forecast(lat, lon)
            tools_called.append({"tool": "get_agricultural_forecast", "args": {"lat": lat, "lon": lon}, "result": agri_data})

        if need_alerts or "alert" in msg_lower or "इशारा" in msg_lower or "चेतावनी" in msg_lower:
            alert_data = await check_location_alerts(lat, lon)
            tools_called.append({"tool": "check_location_alerts", "args": {"lat": lat, "lon": lon}, "result": alert_data})

        reply = self._synthesize_response(language, current_data, agri_data, alert_data, lat, lon)
        
        return {
            "reply": reply,
            "tools_called": tools_called,
            "model": self.model_name or "weathergpt",
            "status": "success"
        }

    def _synthesize_response(self, lang: str, current: Optional[dict], agri: Optional[dict], alerts: Optional[dict], lat: float, lon: float) -> str:
        """Synthesizes structured, voice-ready text in English, Hindi, or Marathi."""
        # Hindi
        if lang == "hi":
            parts = []
            if alerts and alerts.get("active_alerts_count", 0) > 0:
                for a in alerts["alerts"]:
                    parts.append(f"⚠️ मौसम चेतावनी: {a['description']} (वैध: {a.get('active_until')})")
            elif alerts and alerts.get("status") == "success" and not current and not agri:
                parts.append("मौसम चेतावनी: वर्तमान में आपके क्षेत्र के लिए कोई सक्रिय गंभीर मौसम चेतावनी नहीं है। मौसम सामान्य है।")
            if current and current.get("status") == "success":
                temp = current.get("temperature", "--")
                wind = current.get("wind_speed", "--")
                parts.append(f"वर्तमान मौसम: तापमान {temp}°C है और हवा की गति {wind} किमी/घंटा है।")
            if agri and agri.get("status") == "success":
                precip = agri.get("forecast_7_days", {}).get("precipitation_probability_pct", [0])[0]
                soil = agri.get("soil_moisture_surface_m3_m3", "--")
                parts.append(f"कृषि सलाह: मिट्टी में नमी {soil} m³/m³ है। आज बारिश की संभावना {precip}% है।")
                if precip > 60:
                    parts.append("सलाह: भारी बारिश की संभावना के कारण कीटनाशक का छिड़काव या यूरिया डालने का काम टाल दें।")
                else:
                    parts.append("सलाह: मौसम सामान्य है, आप खेत में आवश्यक कार्य कर सकते हैं।")
            return "\n\n".join(parts) if parts else "आपके स्थान के लिए मौसम का डेटा उपलब्ध नहीं हो सका।"

        # Marathi
        elif lang == "mr":
            parts = []
            if alerts and alerts.get("active_alerts_count", 0) > 0:
                for a in alerts["alerts"]:
                    parts.append(f"⚠️ हवामान इशारा: {a['description']} (मुदत: {a.get('active_until')})")
            elif alerts and alerts.get("status") == "success" and not current and not agri:
                parts.append("हवामान इशारा: सध्या आपल्या भागासाठी कोणताही तीव्र हवामान इशारा जारी केलेला नाही. परिस्थिती सामान्य आहे.")
            if current and current.get("status") == "success":
                temp = current.get("temperature", "--")
                wind = current.get("wind_speed", "--")
                parts.append(f"सध्याचे हवामान: तापमान {temp}°C असून वाऱ्याचा वेग {wind} किमी/तास आहे.")
            if agri and agri.get("status") == "success":
                precip = agri.get("forecast_7_days", {}).get("precipitation_probability_pct", [0])[0]
                soil = agri.get("soil_moisture_surface_m3_m3", "--")
                parts.append(f"शेती सल्ला: जमिनीतील ओलावा {soil} m³/m³ आहे आणि आज पावसाची शक्यता {precip}% आहे.")
                if precip > 60:
                    parts.append("सल्ला: आज पावसाची दाट शक्यता असल्याने कीटकनाशक फवारणी किंवा खत व्यवस्थापन पुढे ढकलावे.")
                else:
                    parts.append("सल्ला: हवामान शेतीकामासाठी अनुकूल आहे. वेळेवर आंतरमशागत आणि पाणी व्यवस्थापन करा.")
            return "\n\n".join(parts) if parts else "आपल्या ठिकाणची हवामान माहिती मिळवण्यात अडचण आली."

        # English (default)
        else:
            parts = []
            if alerts and alerts.get("active_alerts_count", 0) > 0:
                for a in alerts["alerts"]:
                    parts.append(f"⚠️ Active Weather Alert: {a['description']} (Valid until: {a.get('active_until')})")
            elif alerts and alerts.get("status") == "success" and not current and not agri:
                parts.append("Weather Alerts: There are currently no active severe weather alerts for your area.")
            if current and current.get("status") == "success":
                temp = current.get("temperature", "--")
                wind = current.get("wind_speed", "--")
                parts.append(f"Current Weather: Temperature is {temp}°C with wind speed at {wind} km/h.")
            if agri and agri.get("status") == "success":
                precip = agri.get("forecast_7_days", {}).get("precipitation_probability_pct", [0])[0]
                soil = agri.get("soil_moisture_surface_m3_m3", "--")
                parts.append(f"Agricultural Advisory: Surface soil moisture is {soil} m³/m³ and today's rain probability is {precip}%.")
                if precip > 60:
                    parts.append("Actionable Advice: High probability of precipitation. Defer foliar pesticide spraying and fertilizer top-dressing.")
                else:
                    parts.append("Actionable Advice: Weather is suitable for field operations. Maintain optimal irrigation schedule.")
            return "\n\n".join(parts) if parts else "Unable to retrieve weather data for the specified coordinates."


weather_agent = WeatherAgent()
