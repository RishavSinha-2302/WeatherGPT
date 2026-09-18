"""
WeatherGPT - WMO WIS 2.0 MQTT Alert Ingestion Worker
Listens to public WMO WIS 2.0 MQTT topics (e.g., cache/a/wis2/#),
extracts severe weather warning geometries (bounding boxes / GeoJSON polygons),
and stores them into the Supabase PostGIS `alerts` table.
"""

import os
import sys
import json
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional
from dotenv import load_dotenv

import paho.mqtt.client as mqtt

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] WIS2-MQTT: %(message)s")
logger = logging.getLogger("wis2_mqtt")

# Configuration
BROKER_HOST = os.getenv("WIS2_BROKER_HOST", "broker.emqx.io")  # Public MQTT broker / WIS2 node
BROKER_PORT = int(os.getenv("WIS2_BROKER_PORT", "1883"))
MQTT_TOPIC = os.getenv("WIS2_MQTT_TOPIC", "cache/a/wis2/#")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "") or os.getenv("SUPABASE_ANON_KEY", "")

supabase_client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Connected to Supabase for alert persistence.")
    except Exception as e:
        logger.warning(f"Could not connect to Supabase: {e}. Alerts will be logged locally.")


def bbox_to_geojson_polygon(bbox: list) -> dict:
    """Converts [min_lon, min_lat, max_lon, max_lat] to GeoJSON Polygon."""
    min_lon, min_lat, max_lon, max_lat = bbox
    return {
        "type": "Polygon",
        "coordinates": [[
            [min_lon, min_lat],
            [max_lon, min_lat],
            [max_lon, max_lat],
            [min_lon, max_lat],
            [min_lon, min_lat]
        ]]
    }


def parse_wis2_payload(raw_data: str) -> Optional[Dict[str, Any]]:
    """
    Parses WMO WIS 2.0 notification payload.
    Supports GeoJSON Feature format and standard WMO notification schema.
    """
    try:
        data = json.loads(raw_data)
    except Exception as e:
        logger.debug(f"Non-JSON message discarded: {e}")
        return None

    # Check for GeoJSON feature
    geometry = data.get("geometry")
    properties = data.get("properties", {})
    bbox = data.get("bbox")

    # If bbox provided without geometry
    if not geometry and bbox and len(bbox) == 4:
        geometry = bbox_to_geojson_polygon(bbox)

    if not geometry:
        return None

    severity = properties.get("severity", "severe").lower()
    if severity not in ["advisory", "watch", "warning", "severe", "extreme"]:
        severity = "severe"

    description = (
        properties.get("description")
        or properties.get("title")
        or properties.get("headline")
        or "Severe Weather Hazard Bulletin from WMO WIS 2.0"
    )

    # Calculate active_until timestamp
    active_until = properties.get("end_datetime") or properties.get("expires")
    if not active_until:
        active_until = (datetime.now(timezone.utc) + timedelta(hours=48)).isoformat()

    return {
        "severity": severity,
        "geometry": geometry,
        "description": description,
        "active_until": active_until,
        "source": properties.get("centre_id", "WMO WIS 2.0")
    }


def save_alert_to_supabase(alert: Dict[str, Any]) -> bool:
    """Persists alert with PostGIS geometry into Supabase."""
    logger.info(f"🚨 New Hazard Alert: [{alert['severity'].upper()}] {alert['description']}")

    if not supabase_client:
        logger.info("ℹ️ Supabase not configured: Alert logged locally. (Set SUPABASE_URL and SUPABASE_KEY in .env)")
        return True

    try:
        # GeoJSON is directly accepted by Supabase / PostGIS for geometry columns
        record = {
            "severity": alert["severity"],
            "polygon_area": alert["geometry"],
            "description": alert["description"],
            "active_until": alert["active_until"],
            "source": alert.get("source", "WIS 2.0")
        }
        res = supabase_client.table("alerts").insert(record).execute()
        logger.info(f"Successfully inserted alert into Supabase PostGIS: {res.data}")
        return True
    except Exception as e:
        logger.error(f"Failed to insert alert into Supabase: {e}")
        return False


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info(f"Connected to WIS 2.0 MQTT Broker ({BROKER_HOST}:{BROKER_PORT})")
        client.subscribe(MQTT_TOPIC)
        logger.info(f"Subscribed to topic: {MQTT_TOPIC}")
    else:
        logger.error(f"Failed to connect to MQTT broker, return code {rc}")


def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode("utf-8")
        alert = parse_wis2_payload(payload_str)
        if alert:
            save_alert_to_supabase(alert)
    except Exception as e:
        logger.error(f"Error handling message on {msg.topic}: {e}")


def simulate_alert_ingestion():
    """Generates and ingests a simulated WMO WIS 2.0 severe weather alert."""
    logger.info("Running simulated WIS 2.0 severe weather alert ingestion...")
    simulated_payload = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [73.65, 18.35],
                [74.15, 18.35],
                [74.15, 18.75],
                [73.65, 18.75],
                [73.65, 18.35]
            ]]
        },
        "properties": {
            "title": "WMO WIS 2.0 Flash Flood & Gale Wind Warning",
            "severity": "extreme",
            "description": "Red Warning: Extreme precipitation (>115 mm) and squally winds expected over Western Maharashtra watershed.",
            "centre_id": "WIS2-IN-IMD",
            "expires": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        }
    }
    
    alert = parse_wis2_payload(json.dumps(simulated_payload))
    if alert:
        save_alert_to_supabase(alert)
        logger.info("Simulation completed successfully!")


def start_listener():
    """Starts the continuous MQTT listener loop."""
    try:
        # Paho MQTT 2.0+ CallbackAPIVersion
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="weathergpt_wis2_worker")
    except AttributeError:
        client = mqtt.Client(client_id="weathergpt_wis2_worker")

    client.on_connect = on_connect
    client.on_message = on_message

    logger.info(f"Connecting to WIS 2.0 broker at {BROKER_HOST}:{BROKER_PORT}...")
    try:
        client.connect(BROKER_HOST, BROKER_PORT, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Stopping WIS 2.0 MQTT listener...")
        client.disconnect()
    except Exception as e:
        logger.error(f"WIS 2.0 listener error: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--simulate":
        simulate_alert_ingestion()
    else:
        start_listener()
