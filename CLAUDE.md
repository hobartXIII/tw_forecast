## Streamlit 開發慣例

### 核心執行模型
- 腳本**每次互動都從頭重跑**（不是 request/response 模板渲染）。
- 跨重跑保存狀態 → `st.session_state`。
- 昂貴運算務必快取：`@st.cache_data`（資料）、`@st.cache_resource`（連線/模型）。
- 效能鐵則：局部即時更新用 `@st.fragment` 或 `st.empty()`，別讓整支腳本陪跑。

### 美化：兩條路線分工
- **版面配色、主題** → 原生 `.streamlit/config.toml` 的 `[theme]`（一致性高、自動顧無障礙對比、存檔即 live-reload）。
- **元件級視覺效果、單格樣式** → CSS，透過 `st.markdown(..., unsafe_allow_html=True)`。

#### config.toml 主題
```toml
[theme]
base = "light"                        # 繼承 light/dark，只覆寫要改的
primaryColor = "#..."                 # 互動元件強調色
backgroundColor = "#..."              # 主內容區背景
secondaryBackgroundColor = "#..."     # 側欄與多數 widget 背景
textColor = "#..."
font = "sans serif"                   # sans serif | serif | monospace
# 進階：linkColor / headingFont / codeFont / 圓角 radius /
#       [[theme.fontFace]] 自訂字型 / [theme.sidebar] 側欄獨立主題
```
- 顏色接受任何 CSS 色值（hex / 色名 / RGB / HSL）。
- 侷限：只能改「主色、背景、文字」語意角色，無法針對單一元件精細調樣式。

#### 玻璃效果（glassmorphism）→ 一定走 CSS
```python
st.markdown("""
<style>
.glass {
    background: rgba(255,255,255,0.15);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);   /* Safari */
    border: 1px solid rgba(255,255,255,0.25);
    border-radius: 16px; padding: 20px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.1);
}
</style>
""", unsafe_allow_html=True)
st.markdown('<div class="glass">內容</div>', unsafe_allow_html=True)
```
- 背景要有漸層/圖片才透得出模糊，純白底看不出來。
- 想讓「原生 widget」變玻璃較 hack，自畫 `<div>` 最單純。

#### 依數值區間變色
單一數值 / KPI / 狀態燈號 → 拆成 function：
```python
def color_by_range(v):
    return "red" if v >= 80 else "orange" if v >= 50 else "green"

st.markdown(f":{color_by_range(score)}[{score} 分]")   # 原生彩色 Markdown
st.badge(f"{score} 分", color=color_by_range(score))    # 彩色標籤
```
- 原生色名固定一組：red / orange / yellow / green / blue / violet / gray / primary。
- `:color-background[文字]` 做底色高亮。
- 要任意 hex → 改用 `<span style="color:...">`（需 unsafe_allow_html）。

表格逐格依值變色 → pandas Styler（不需 unsafe_allow_html）：
```python
def highlight(val):
    if val >= 80:   return "background-color:#fdecea; color:#c0392b"
    elif val >= 50: return "background-color:#fef5e7; color:#b9770e"
    else:           return "background-color:#eafaf1; color:#1e8449"

st.dataframe(df.style.map(highlight, subset=["分數"]))
```
- `.style.map()` 逐格套（舊版 `.applymap`）；`.style.apply()` 整欄/列一起判斷。
- 連續漸層可用現成 `.style.background_gradient()`。
- Styler 只吃 inline style、不吃具名 class；要用具名 class 得整個表格自己畫 HTML。

### 常用 st 元件速查

**文字與顯示**
```python
st.write(任何東西)          # 萬用，自動判斷型別（str/df/圖/dict…）
st.title / st.header / st.subheader / st.caption
st.markdown("...", unsafe_allow_html=True)
st.code(code, language="python")
st.metric("營收", "1.2M", "+5%")             # 大數字＋增減
st.badge("狀態", color="green")
st.divider()
```

**輸入元件（回傳值即使用者輸入）**
```python
st.text_input / st.text_area / st.number_input
st.slider / st.select_slider
st.selectbox / st.multiselect / st.radio
st.checkbox / st.toggle
st.pills / st.segmented_control            # 單選/多選按鈕組
st.date_input / st.time_input / st.color_picker
st.file_uploader / st.camera_input
st.button / st.download_button / st.link_button
st.feedback("stars")
```

**版面**
```python
col1, col2 = st.columns(2)
with col1: ...
tab1, tab2 = st.tabs(["總覽", "明細"])
with st.expander("展開看更多"): ...
with st.container(border=True): ...          # 可加邊框當卡片
with st.sidebar: ...
with st.popover("點我"): ...
ph = st.empty()                              # 佔位，之後可覆寫內容
```

**資料與圖表**
```python
st.dataframe(df)                             # 互動表格（可排序）
st.dataframe(df.style.map(fn, subset=[...])) # 依值上色
st.data_editor(df)                           # 可編輯表格，回傳改後 df
st.table(df)                                 # 靜態表
st.line_chart / st.bar_chart / st.area_chart / st.scatter_chart / st.map
st.plotly_chart(fig) / st.altair_chart(fig) / st.pyplot(fig)
st.image / st.audio / st.video
```

**狀態與回饋**
```python
st.success / st.info / st.warning / st.error
st.toast("已儲存")                           # 右下角浮動提示
with st.spinner("處理中…"): ...
with st.status("執行中…") as s:
    ...; s.update(label="完成", state="complete")
st.progress(0.7)
```

**聊天介面（LLM / RAG 常用）**
```python
prompt = st.chat_input("輸入訊息")
with st.chat_message("user"): st.write(prompt)
with st.chat_message("assistant"):
    st.write_stream(生成器)                  # 串流逐字輸出
```

**流程控制**
```python
with st.form("f"):                           # 表單：內部元件不觸發重跑，
    x = st.text_input("欄位")                # 按 submit 才一次送出
    if st.form_submit_button("送出"): ...

@st.dialog("標題")                           # 彈窗（modal）
def my_dialog(): ...

@st.fragment                                 # 片段重跑：只重跑這塊
def part(): ...

st.rerun()                                   # 手動觸發重跑
st.stop()                                    # 從此中止本次執行
```

**多頁 app**
```python
pg = st.navigation([st.Page("home.py"), st.Page("report.py")])
pg.run()
st.page_link("report.py", label="報表")
```

### Community Cloud 部署限制
- 每個 app 資源上限約 2.7 GB；私有 app 限 1 個、公開無限。
- 超量會被暫時鎖住 → 用 `st.cache_data` / `st.cache_resource`、限制 `ttl`/`max_entries`、大資料移資料庫。
- `st.file_uploader` 預設上限 200MB → 靠 `.streamlit/config.toml` 的 `server.maxUploadSize` 調。
- Pro/付費版指的是 Snowflake 上代管；Community Cloud 本身只有免費方案。


## 本專案開發流程

> 上面是 Streamlit 通用慣例；以下是這個 repo 的實際做法。完整說明見 `forecast/ARCHITECTURE.md`（每個檔案的功能與修改對照表）與 `forecast/SPECIFICATION.md`。

- **程式位置**：正式程式碼在 `forecast/src/tw_forecast/`（`backend/` 是 GitHub Actions 的流程一、`frontend/` 是 Streamlit 儀表板），入口只有 `forecast/scripts/fetch_and_store.py` 與 `forecast/streamlit_app/app.py`，兩者只負責串接。
- **先分析、後修改**：新想法先說明原因與方案、等使用者同意再改程式。
- **測試**：在 `forecast/` 執行 `python -m pytest`（不連網、不連資料庫）。新功能同時補測試；純函式寫單元測試，畫面流程用 `tests/frontend/test_app_smoke.py` 的 `AppTest`。需要真實連線的檢查放 `forecast/checks/`，維運工具放 `forecast/tools/`。
- **改 `src/` 後要重啟 `streamlit run`**，否則可能沿用舊模組而出現 `ImportError`。
- **前端只能用 `anon` 金鑰**；金鑰與密碼不可進程式碼、日誌或錯誤訊息（用 `mask_secrets`／`translate_error` 遮蔽）。
- **分支**：重構前的版本保留在 `old` 分支；`streamlit` 分支是 Community Cloud 部署的 Streamlit 版（已關閉「立即更新」）。
- **Vercel 改寫**：在 `main` 進行，規劃與決定見 `forecast/VERCEL_PLAN.md`。
