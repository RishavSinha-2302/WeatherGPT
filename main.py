"""
WeatherGPT FastAPI Main Server
Provides REST endpoints for conversational AI routing, real-time NWP weather data,
and serves the mobile-first frontend.
"""

import os
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from agent import weather_agent
from tools import get_current_weather, check_location_alerts

load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("weathergpt.api")

app = FastAPI(
    title="WeatherGPT API",
    description="Conversational AI routing user queries to Numerical Weather Prediction (NWP) models and WMO WIS 2.0 alerts",
    version="1.0.0"
)

# CORS Middleware to support flexible deployment
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request / Response Schemas
class ChatRequest(BaseModel):
    user_id: Optional[str] = Field(default="user_guest", description="Unique user identifier")
    message: str = Field(..., description="User voice transcript or text query")
    lat: float = Field(..., description="User latitude (e.g., 18.5204 for Pune)")
    lon: float = Field(..., description="User longitude (e.g., 73.8567 for Pune)")
    language: Optional[str] = Field(default="en", description="Target language ('en', 'hi', 'mr')")

class ChatResponse(BaseModel):
    reply: str
    tools_called: List[Dict[str, Any]]
    model: str
    status: str

# API Endpoints
@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatRequest):
    """
    Main conversational endpoint:
    Accepts user message, coordinates, and language preference,
    routes to Gemini 1.5 Flash tool-calling router, and returns translated advice.
    """
    if not payload.message or not payload.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    
    logger.info(f"Received chat request from {payload.user_id} at ({payload.lat}, {payload.lon}) [{payload.language}]: {payload.message}")
    
    try:
        result = await weather_agent.chat(
            user_message=payload.message,
            lat=payload.lat,
            lon=payload.lon,
            language=payload.language or "en"
        )
        return ChatResponse(**result)
    except Exception as e:
        logger.error(f"Error processing chat request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process query: {str(e)}")


@app.get("/api/weather/quick")
async def quick_weather(lat: float, lon: float):
    """
    Returns quick snapshot of current weather and active hazard alerts
    to render ambient status banner in the frontend header.
    """
    current = await get_current_weather(lat, lon)
    alerts = await check_location_alerts(lat, lon)
    return {
        "current": current,
        "alerts": alerts
    }


@app.get("/api/health")
async def health_check():
    """System health check and diagnostic status."""
    return {
        "status": "healthy",
        "service": "WeatherGPT",
        "version": "1.0.0",
        "gemini_configured": bool(os.getenv("GEMINI_API_KEY")),
        "supabase_configured": bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY")),
        "stack": "FastAPI + Open-Meteo + PostGIS + Gemini 1.5 Flash"
    }


# Static Files Setup: Serve mobile-first React/Tailwind frontend
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def serve_index():
    """Serves the main single-page web app."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(
            str(index_path),
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0"
            }
        )
    return JSONResponse(
        content={
            "message": "WeatherGPT API running. static/index.html is being prepared.",
            "docs": "/docs"
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
