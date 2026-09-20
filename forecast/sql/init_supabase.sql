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

-- 資料庫預設時區設為台灣：timestamptz 內部仍以 UTC 儲存，此設定只影響查詢結果的顯示（顯示為 +08:00）
-- 對新連線生效（Supabase 資料庫名稱為 postgres）；已開啟的 SQL Editor 分頁需重新整理
ALTER DATABASE postgres SET timezone TO 'Asia/Taipei';
ALTER ROLE authenticator SET timezone TO 'Asia/Taipei';  -- PostgREST / supabase-py 連線所用角色

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

-- 流程一執行狀態：排程 (schedule) 與手動 (manual) 各一列，記錄「最後一次成功更新」的時間。
-- 儀表板的「立即更新」以此表判斷距上次更新是否已滿間隔（見 SPECIFICATION.md §8.1）。
CREATE TABLE IF NOT EXISTS public.pipeline_status (
    trigger_type TEXT PRIMARY KEY CHECK (trigger_type IN ('schedule', 'manual')),
    last_success_at TIMESTAMPTZ,          -- 最後一次成功寫入預報的時間（與該批預報的 updated_at 相同）
    last_run_at TIMESTAMPTZ,              -- 最後一次執行的時間（成功或失敗）
    last_status TEXT CHECK (last_status IN ('success', 'failed')),
    last_error TEXT                       -- 失敗時的簡短訊息
);

-- 初始資料：讓表一建立就有列可讀（前端讀不到就不放行手動更新）。
-- 既有預報都是手動執行寫入的，因此以現有預報的最新 updated_at 填入 manual；schedule 尚無紀錄。
INSERT INTO public.pipeline_status (trigger_type, last_success_at, last_run_at, last_status)
SELECT 'manual', max(updated_at), max(updated_at), CASE WHEN max(updated_at) IS NULL THEN NULL ELSE 'success' END
FROM public.weather_forecasts
ON CONFLICT (trigger_type) DO NOTHING;
INSERT INTO public.pipeline_status (trigger_type) VALUES ('schedule') ON CONFLICT (trigger_type) DO NOTHING;

-- RLS：啟用後僅開放 anon 唯讀；寫入一律由 service_role (繞過 RLS) 執行
ALTER TABLE public.pipeline_status ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow anon read only" ON public.pipeline_status;
CREATE POLICY "Allow anon read only" ON public.pipeline_status
    FOR SELECT TO anon USING (true);

-- RLS：啟用後僅開放 anon 唯讀；寫入一律由 service_role (繞過 RLS) 執行
ALTER TABLE public.weather_forecasts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow anon read only" ON public.weather_forecasts;
CREATE POLICY "Allow anon read only" ON public.weather_forecasts
    FOR SELECT TO anon USING (true);
