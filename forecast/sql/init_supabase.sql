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


-- ============================================================
-- 告警設定（SPECIFICATION.md §5.1）
-- 只有排程腳本以 service_role 讀取；anon 完全讀不到也寫不了（RLS 不建任何 policy，並撤銷權限）。
-- 預設「所有縣市關閉」＝不發送；要收哪個縣市的告警，把該縣市的 enabled 改為 true。
-- ============================================================

-- 縣市告警設定：縣市為主鍵；降雨／低溫／高溫三個條件各自有開關與門檻
CREATE TABLE IF NOT EXISTS public.alert_city_settings (
    location_name TEXT PRIMARY KEY,                  -- 縣市（與氣象署 LocationName 一致，如 臺北市）
    enabled BOOLEAN NOT NULL DEFAULT false,          -- 該縣市是否發送告警（預設關閉）
    rain_enabled BOOLEAN NOT NULL DEFAULT true,      -- 降雨條件開關
    rain_threshold INTEGER NOT NULL DEFAULT 60 CHECK (rain_threshold BETWEEN 0 AND 100),        -- 降雨機率 >= 此值
    min_temp_enabled BOOLEAN NOT NULL DEFAULT true,  -- 低溫條件開關
    min_temp_threshold NUMERIC(4, 1) NOT NULL DEFAULT 12 CHECK (min_temp_threshold BETWEEN -20 AND 50),  -- 最低溫 <= 此值
    max_temp_enabled BOOLEAN NOT NULL DEFAULT true,  -- 高溫條件開關
    max_temp_threshold NUMERIC(4, 1) NOT NULL DEFAULT 35 CHECK (max_temp_threshold BETWEEN -20 AND 50), -- 最高溫 >= 此值
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 發送時段設定：只在啟用的時段（須是排程時槽）發送
CREATE TABLE IF NOT EXISTS public.alert_slot_settings (
    slot TEXT PRIMARY KEY CHECK (slot IN ('08:45', '14:45', '20:45')),  -- 台灣時間
    enabled BOOLEAN NOT NULL DEFAULT true,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 初始資料（已存在的列不會被覆蓋）：22 縣市全部關閉、三個發送時段全部啟用
INSERT INTO public.alert_city_settings (location_name) VALUES
    ('臺北市'), ('新北市'), ('基隆市'), ('桃園市'), ('新竹市'), ('新竹縣'),
    ('苗栗縣'), ('臺中市'), ('彰化縣'), ('南投縣'), ('雲林縣'),
    ('嘉義市'), ('嘉義縣'), ('臺南市'), ('高雄市'), ('屏東縣'),
    ('宜蘭縣'), ('花蓮縣'), ('臺東縣'),
    ('澎湖縣'), ('金門縣'), ('連江縣')
ON CONFLICT (location_name) DO NOTHING;
INSERT INTO public.alert_slot_settings (slot) VALUES ('08:45'), ('14:45'), ('20:45')
ON CONFLICT (slot) DO NOTHING;

-- 鎖住：啟用 RLS 且不建立任何 policy，另撤銷 anon / authenticated 的所有權限（雙重保護）
ALTER TABLE public.alert_city_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alert_slot_settings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.alert_city_settings FROM anon, authenticated;
REVOKE ALL ON public.alert_slot_settings FROM anon, authenticated;

-- 更新時自動刷新 updated_at（沿用上方的 set_updated_at）
DROP TRIGGER IF EXISTS trg_alert_city_settings_updated_at ON public.alert_city_settings;
CREATE TRIGGER trg_alert_city_settings_updated_at
    BEFORE UPDATE ON public.alert_city_settings
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
DROP TRIGGER IF EXISTS trg_alert_slot_settings_updated_at ON public.alert_slot_settings;
CREATE TRIGGER trg_alert_slot_settings_updated_at
    BEFORE UPDATE ON public.alert_slot_settings
    FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();

-- 用法範例（在 Supabase SQL Editor 執行；管理頁面完成前先用這種方式調整）：
--   啟用臺北市：           UPDATE public.alert_city_settings SET enabled = true WHERE location_name = '臺北市';
--   臺北市降雨門檻改 70：   UPDATE public.alert_city_settings SET rain_threshold = 70 WHERE location_name = '臺北市';
--   關閉臺北市的低溫條件： UPDATE public.alert_city_settings SET min_temp_enabled = false WHERE location_name = '臺北市';
--   全部縣市啟用：         UPDATE public.alert_city_settings SET enabled = true;
--   關閉 14:45 發送：      UPDATE public.alert_slot_settings SET enabled = false WHERE slot = '14:45';
