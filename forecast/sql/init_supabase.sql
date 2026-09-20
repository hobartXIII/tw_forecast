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


-- ============================================================
-- 管理者密碼與告警設定函式（第 2 階段；SPECIFICATION.md §5.1、§8.1）
-- 管理者密碼的 bcrypt 雜湊存在 private schema（不對 API 開放）；頁面呼叫下面兩個函式時帶入密碼，
-- 由資料庫比對雜湊，密碼正確才讀取／寫入告警設定。anon 只能「呼叫函式」，不能直接碰任何設定表。
-- ============================================================
CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;

CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC, anon, authenticated;

CREATE TABLE IF NOT EXISTS private.admin_credential (
    id INTEGER PRIMARY KEY CHECK (id = 1),                    -- 只有一位管理者
    password_hash TEXT NOT NULL CHECK (password_hash LIKE '$2a$%' OR password_hash LIKE '$2b$%' OR password_hash LIKE '$2y$%'),  -- bcrypt 雜湊，絕不存明文
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE private.admin_credential ENABLE ROW LEVEL SECURITY;      -- 不建立任何 policy
REVOKE ALL ON private.admin_credential FROM PUBLIC, anon, authenticated;

-- 驗證密碼（僅供下面兩個函式內部呼叫）：錯誤、未設定、空值一律延遲 1 秒後拒絕，讓連續猜測變慢
CREATE OR REPLACE FUNCTION private.verify_admin(p_password TEXT)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_hash TEXT;
BEGIN
    SELECT password_hash INTO v_hash FROM private.admin_credential WHERE id = 1;
    IF v_hash IS NULL OR p_password IS NULL OR p_password = ''
       OR extensions.crypt(p_password, v_hash) IS DISTINCT FROM v_hash THEN   -- NULL 也視為不符（無法確定就拒絕）
        PERFORM pg_sleep(1);
        RAISE EXCEPTION 'invalid_password' USING ERRCODE = '28P01';
    END IF;
END;
$$;
REVOKE ALL ON FUNCTION private.verify_admin(TEXT) FROM PUBLIC, anon, authenticated;

-- 讀取告警設定（密碼正確才回傳）
CREATE OR REPLACE FUNCTION public.admin_get_alert_settings(p_password TEXT)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
    PERFORM private.verify_admin(p_password);
    RETURN jsonb_build_object(
        'cities', (SELECT COALESCE(jsonb_agg(to_jsonb(c) ORDER BY c.location_name), '[]'::jsonb)
                   FROM public.alert_city_settings c),
        'slots',  (SELECT COALESCE(jsonb_agg(to_jsonb(s) ORDER BY s.slot), '[]'::jsonb)
                   FROM public.alert_slot_settings s));
END;
$$;

-- 儲存告警設定（密碼正確才寫入）：只更新既有的縣市與發送時段（不能新增或刪除），
-- 數值範圍由資料表的 CHECK 把關；兩張表在同一個交易內更新，失敗時全部回復
CREATE OR REPLACE FUNCTION public.admin_save_alert_settings(p_password TEXT, p_cities JSONB, p_slots JSONB)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
    v_cities INTEGER;
    v_slots INTEGER;
BEGIN
    PERFORM private.verify_admin(p_password);
    IF p_cities IS NULL OR jsonb_typeof(p_cities) <> 'array' OR jsonb_array_length(p_cities) > 100
       OR p_slots IS NULL OR jsonb_typeof(p_slots) <> 'array' OR jsonb_array_length(p_slots) > 10 THEN
        RAISE EXCEPTION 'invalid_payload' USING ERRCODE = '22023';
    END IF;

    UPDATE public.alert_city_settings AS t SET
        enabled = r.enabled,
        rain_enabled = r.rain_enabled, rain_threshold = r.rain_threshold,
        min_temp_enabled = r.min_temp_enabled, min_temp_threshold = r.min_temp_threshold,
        max_temp_enabled = r.max_temp_enabled, max_temp_threshold = r.max_temp_threshold
    FROM jsonb_to_recordset(p_cities) AS r(
        location_name TEXT, enabled BOOLEAN, rain_enabled BOOLEAN, rain_threshold INTEGER,
        min_temp_enabled BOOLEAN, min_temp_threshold NUMERIC, max_temp_enabled BOOLEAN, max_temp_threshold NUMERIC)
    WHERE t.location_name = r.location_name;
    GET DIAGNOSTICS v_cities = ROW_COUNT;

    UPDATE public.alert_slot_settings AS t SET enabled = r.enabled
    FROM jsonb_to_recordset(p_slots) AS r(slot TEXT, enabled BOOLEAN)
    WHERE t.slot = r.slot;
    GET DIAGNOSTICS v_slots = ROW_COUNT;

    RETURN jsonb_build_object('cities', v_cities, 'slots', v_slots);
END;
$$;

-- 只有 anon（前端使用的角色）能呼叫這兩個函式；PUBLIC 預設的執行權限一併撤銷
REVOKE ALL ON FUNCTION public.admin_get_alert_settings(TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.admin_save_alert_settings(TEXT, JSONB, JSONB) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.admin_get_alert_settings(TEXT) TO anon;
GRANT EXECUTE ON FUNCTION public.admin_save_alert_settings(TEXT, JSONB, JSONB) TO anon;

-- 設定／更換管理者密碼（在 SQL Editor 執行）。雜湊值請用 python scripts/make_admin_hash.py 在本機產生，
-- 不要把密碼明文貼進 SQL Editor（查詢紀錄會保留）：
--   INSERT INTO private.admin_credential (id, password_hash) VALUES (1, '<雜湊值>')
--   ON CONFLICT (id) DO UPDATE SET password_hash = EXCLUDED.password_hash, updated_at = now();
-- 相容性檢查（雜湊值格式是否被 pgcrypto 接受）：python scripts/make_admin_hash.py --selftest 會印出可直接執行的 SQL。
