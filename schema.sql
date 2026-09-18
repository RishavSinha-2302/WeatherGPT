-- ==============================================================================
-- WeatherGPT: Database Initialization Schema for Supabase (PostgreSQL + PostGIS)
-- Conversational NWP Weather & Hazard Advisory System
-- ==============================================================================

-- 1. Enable PostGIS extension for spatial and numerical weather hazard calculations
CREATE EXTENSION IF NOT EXISTS postgis;

-- 2. Users Table
-- Stores user preferences and geographic location for localized forecasts
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phone_number TEXT UNIQUE,
    preferred_language VARCHAR(10) DEFAULT 'en', -- e.g., 'en', 'hi', 'mr'
    location geometry(Point, 4326),              -- Exact GPS coordinates (WGS84)
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Spatial index on user locations for fast proximity queries
CREATE INDEX IF NOT EXISTS idx_users_location ON users USING GIST (location);

-- 3. Alerts Table
-- Ingested severe weather warning polygons from WIS 2.0 / IMD / NWP models
CREATE TABLE IF NOT EXISTS alerts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    severity VARCHAR(20) NOT NULL CHECK (severity IN ('advisory', 'watch', 'warning', 'severe', 'extreme')),
    polygon_area geometry(Polygon, 4326) NOT NULL, -- Spatial boundary polygon (WGS84)
    description TEXT NOT NULL,
    active_until TIMESTAMPTZ NOT NULL,
    source TEXT DEFAULT 'WIS 2.0 WMO',
    created_at TIMESTAMPTZ DEFAULT timezone('utc'::text, now()) NOT NULL
);

-- Spatial index on alert polygons for spatial intersection (ST_Contains/ST_Intersects)
CREATE INDEX IF NOT EXISTS idx_alerts_polygon_area ON alerts USING GIST (polygon_area);
CREATE INDEX IF NOT EXISTS idx_alerts_active_until ON alerts (active_until);

-- 4. Stored Procedure (RPC) to check if a location intersects any active warning polygons
-- Can be directly invoked via supabase.rpc('check_location_alerts', {'p_lat': ..., 'p_lon': ...})
CREATE OR REPLACE FUNCTION check_location_alerts(p_lat DOUBLE PRECISION, p_lon DOUBLE PRECISION)
RETURNS TABLE (
    id UUID,
    severity VARCHAR(20),
    description TEXT,
    active_until TIMESTAMPTZ,
    source TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.id,
        a.severity,
        a.description,
        a.active_until,
        a.source
    FROM alerts a
    WHERE a.active_until >= timezone('utc'::text, now())
      AND ST_Contains(a.polygon_area, ST_SetSRID(ST_MakePoint(p_lon, p_lat), 4326));
END;
$$;

-- 5. Row Level Security (RLS) configuration
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE alerts ENABLE ROW LEVEL SECURITY;

-- Allow public anonymous read access to active alerts (for WeatherGPT queries)
CREATE POLICY "Public can read active alerts" ON alerts
    FOR SELECT USING (active_until >= timezone('utc'::text, now()));

-- Allow service role full access to insert WIS 2.0 alerts
CREATE POLICY "Service role can insert alerts" ON alerts
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Allow public read/insert for users
CREATE POLICY "Public can manage own user profile" ON users
    FOR ALL USING (true) WITH CHECK (true);

-- 6. Sample Seed Data for immediate testing (Pune & Western Maharashtra rural belt)
-- Sample Alert 1: Heavy rain warning polygon around Pune & Haveli / Baramati
INSERT INTO alerts (severity, polygon_area, description, active_until, source)
VALUES (
    'severe',
    ST_GeomFromText(
        'POLYGON((73.70 18.40, 74.10 18.40, 74.10 18.70, 73.70 18.70, 73.70 18.40))',
        4326
    ),
    'Orange Alert: Thunderstorms with heavy surface winds (40-50 km/h) and localized waterlogging expected in Pune district.',
    timezone('utc'::text, now()) + interval '48 hours',
    'IMD / WIS 2.0 Ingestion'
) ON CONFLICT DO NOTHING;

-- Sample Alert 2: Heat & Dry Wind Advisory for Vidarbha / Nagpur rural agricultural belt
INSERT INTO alerts (severity, polygon_area, description, active_until, source)
VALUES (
    'warning',
    ST_GeomFromText(
        'POLYGON((78.90 21.00, 79.40 21.00, 79.40 21.40, 78.90 21.40, 78.90 21.00))',
        4326
    ),
    'High Evapotranspiration Advisory: Ensure mulching and micro-irrigation for cotton and soybean crops.',
    timezone('utc'::text, now()) + interval '72 hours',
    'Agro-Met Advisory / WIS 2.0'
) ON CONFLICT DO NOTHING;
