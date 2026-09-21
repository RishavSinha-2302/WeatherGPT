"""
WeatherGPT Tools Module
Implements Numerical Weather Prediction (NWP) data fetching via Open-Meteo API
and spatial hazard polygon checking via Supabase PostGIS.
"""

import os
import logging
from typing import Dict, Any, List
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("weathergpt.tools")

# Supabase Client Initialization (optional/graceful fallback)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")

supabase_client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client, Client
        supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase client initialized successfully.")
    except Exception as e:
        logger.warning(f"Failed to initialize Supabase client: {e}. Using local fallback for alerts.")


async def get_current_weather(lat: float, lon: float) -> Dict[str, Any]:
    """
    Fetches real-time current weather data for given geographic coordinates using Open-Meteo.
    
    Args:
        lat: Latitude of the location (e.g. 18.5204 for Pune)
        lon: Longitude of the location (e.g. 73.8567 for Pune)
        
    Returns:
        dict: Real-time weather observation including temperature (°C), wind speed (km/h),
              wind direction, weather code (WMO), and is_day flag.
    """
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            current = data.get("current_weather", {})
            return {
                "latitude": lat,
                "longitude": lon,
                "temperature": current.get("temperature"),
                "wind_speed": current.get("windspeed"),
                "wind_direction": current.get("winddirection"),
                "weather_code": current.get("weathercode"),
                "is_day": current.get("is_day"),
                "time": current.get("time"),
                "status": "success"
            }
    except Exception as e:
        logger.error(f"Error fetching current weather: {e}")
        return {
            "latitude": lat,
            "longitude": lon,
            "error": str(e),
            "status": "failed"
        }

async def get_agricultural_forecast(lat: float, lon: float) -> Dict[str, Any]:
    """
    Fetches agricultural weather data from Open-Meteo for the next 7 days,
    including soil moisture, precipitation probability, daily rainfall,
    wind speed, and relative humidity for farming and crop decisions.
    
    Args:
        lat: Latitude of the farm/field location
        lon: Longitude of the farm/field location
        
    Returns:
        dict: 7-day agricultural forecast with daily precipitation sum, max precipitation probability,
              soil moisture levels (0-1cm and 1-3cm depth), max wind speed, and min/max temperatures.
    """
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        "&daily=precipitation_probability_max,precipitation_sum,wind_speed_10m_max,temperature_2m_max,temperature_2m_min"
        "&hourly=soil_moisture_0_to_1cm,soil_moisture_1_to_3cm,relative_humidity_2m"
        "&timezone=auto&forecast_days=7"
    )
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            
            daily = data.get("daily", {})
            hourly = data.get("hourly", {})
            
            # Aggregate current / average top-layer soil moisture from recent hours
            soil_0_1 = hourly.get("soil_moisture_0_to_1cm", [])
            soil_1_3 = hourly.get("soil_moisture_1_to_3cm", [])
            recent_soil_0_1 = soil_0_1[:24] if soil_0_1 else []
            recent_soil_1_3 = soil_1_3[:24] if soil_1_3 else []
            
            avg_soil_surface = round(sum(recent_soil_0_1) / len(recent_soil_0_1), 3) if recent_soil_0_1 else None
            avg_soil_rootzone = round(sum(recent_soil_1_3) / len(recent_soil_1_3), 3) if recent_soil_1_3 else None
            
            return {
                "latitude": lat,
                "longitude": lon,
                "soil_moisture_surface_m3_m3": avg_soil_surface,
                "soil_moisture_rootzone_m3_m3": avg_soil_rootzone,
                "forecast_7_days": {
                    "dates": daily.get("time", []),
                    "max_temperature_c": daily.get("temperature_2m_max", []),
                    "min_temperature_c": daily.get("temperature_2m_min", []),
                    "precipitation_sum_mm": daily.get("precipitation_sum", []),
                    "precipitation_probability_pct": daily.get("precipitation_probability_max", []),
                    "max_wind_speed_kmh": daily.get("wind_speed_10m_max", [])
                },
                "status": "success"
            }
    except Exception as e:
        logger.error(f"Error fetching agricultural forecast: {e}")
        return {
            "latitude": lat,
            "longitude": lon,
            "error": str(e),
            "status": "failed"
        }

async def check_location_alerts(lat: float, lon: float) -> Dict[str, Any]:
    """
    Fetches real-time weather and severe hazard alerts for given geographic coordinates
    from WeatherAPI alerts endpoint (https://api.weatherapi.com/v1/alerts.json).
    
    Args:
        lat: Latitude of user location
        lon: Longitude of user location
        
    Returns:
        dict: Real-time active hazard alerts (severity, event, description, valid until, source).
    """
    api_key = os.getenv("WEATHERAPI_API_KEY", "").strip()
    if not api_key:
        logger.warning("WEATHERAPI_API_KEY not configured in .env")
        return {
            "latitude": lat,
            "longitude": lon,
            "active_alerts_count": 0,
            "alerts": [],
            "status": "no_key"
        }

    url = f"https://api.weatherapi.com/v1/alerts.json?key={api_key}&q={lat},{lon}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
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
        logger.error(f"Error fetching alerts from WeatherAPI: {e}")
        return {
            "latitude": lat,
            "longitude": lon,
            "active_alerts_count": 0,
            "alerts": [],
            "status": "failed",
            "error": str(e)
        }
