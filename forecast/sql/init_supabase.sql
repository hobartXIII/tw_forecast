-- Supabase 建表腳本：於 Supabase Dashboard → SQL Editor 執行
-- 欄位僅保留 F-D0047-091 各縣市資料提供的欄位 (見 SPECIFICATION.md §3.3 / §5)

CREATE TABLE IF NOT EXISTS public.weather_forecasts (
    location_name VARCHAR(50) NOT NULL,   -- 縣市 (LocationName)
    forecast_time_start TIMESTAMPTZ NOT NULL,
    forecast_time_end TIMESTAMPTZ NOT NULL,
    latitude NUMERIC(9, 6),               -- 縣市緯度 (Location 層級)
    longitude NUMERIC(9, 6),              -- 縣市經度
    weather_condition VARCHAR(100),       -- 天氣現象
    min_temp NUMERIC(4, 1),               -- 最低溫度
    max_temp NUMERIC(4, 1),               -- 最高溫度
    avg_temp NUMERIC(4, 1),               -- 平均溫度
    rain_probability INTEGER,             -- 12 小時降雨機率 (%)，未取得時無此值 (NULL)
    comfort_index VARCHAR(100),           -- 舒適度
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),  -- 資料建立/最後更新時間 (新增時取預設值，更新時由觸發器與程式覆寫)

    -- 以「縣市 + 時段」為主鍵，同一縣市與同時段重複寫入即覆蓋 (upsert)
    PRIMARY KEY (location_name, forecast_time_start, forecast_time_end)
);

CREATE INDEX IF NOT EXISTS idx_weather_forecasts_time ON public.weather_forecasts(forecast_time_start DESC);

-- 既有資料表補欄位（首次建表者可略過；已存在的表會補上，既有列以執行當下時間填入）
ALTER TABLE public.weather_forecasts
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- 每次 UPDATE（含 upsert 走到 ON CONFLICT DO UPDATE）自動刷新 updated_at
CREATE OR REPLACE FUNCTION public.set_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_weather_forecasts_updated_at ON public.weather_forecasts;
CREATE TRIGGER trg_weather_forecasts_updated_at
    BEFORE UPDATE ON public.weather_forecasts
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- RLS：啟用後僅開放 anon 唯讀；寫入一律由 service_role (繞過 RLS) 執行
ALTER TABLE public.weather_forecasts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow anon read only" ON public.weather_forecasts;
CREATE POLICY "Allow anon read only" ON public.weather_forecasts
    FOR SELECT TO anon USING (true);
