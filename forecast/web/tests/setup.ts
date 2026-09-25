/** 整個測試以非台灣時區執行，確保程式不依賴執行環境（瀏覽器、Vercel）的時區；時間一律經 src/lib/time.ts 換算。 */
process.env.TZ = "America/New_York";
