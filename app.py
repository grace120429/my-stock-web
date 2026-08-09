# app.py
import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
import yfinance as yf
import time
import json
import os

# 載入您自訂的子模組
import config
import helpers
import storage
import data_fetcher

# ==================== 頁面基本設定 ====================
st.set_page_config(layout="wide", page_title="台股三大法人飆股選股工具")

# ==================== 網頁美化：隱藏頂部工具列與底部商標 ====================
hide_streamlit_style = """
            <style>
            /* 隱藏頂部黑條、編輯按鈕與 GitHub 貓咪圖示 */
            header {visibility: hidden;}
            /* 隱藏 Streamlit 的主選單按鈕 */
            #MainMenu {visibility: hidden;}
            /* 隱藏網頁最下方的 Made with Streamlit 商標 */
            footer {visibility: hidden;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# 初始化 yfinance 快取 (在 Session State 中，避免網頁重新整理時重複下載)
if "yf_cache" not in st.session_state:
    st.session_state.yf_cache = {}
if "yf_60m_cache" not in st.session_state:
    st.session_state.yf_60m_cache = {}

# ==================== 100% 執行緒安全防阻擋連線產生器 ====================
def create_yf_session():
    """
    捨棄在 Windows 多線程極不穩定的 curl_cffi，
    改用 100% 安全、不當機的標準純 Python requests Session。
    配備 Chrome 偽裝標頭，完美防止 Yahoo 429 阻擋！
    """
    import requests as std_requests
    session = std_requests.Session()
    session.verify = False
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    })
    return session

# ==================== 留言區檔案讀寫輔助函數 ====================
COMMENTS_FILE = "comments.json"

def load_comments():
    """載入留言"""
    if not os.path.exists(COMMENTS_FILE):
        return []
    try:
        with open(COMMENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_comments(comments):
    """儲存留言"""
    try:
        with open(COMMENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(comments, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"儲存留言失敗: {e}")

# ==================== 網頁專用精美 HTML 除息行事曆渲染器 ====================
def render_streamlit_calendar(year, month, events):
    """
    利用純 HTML 渲染除息行事曆，支援瀏覽器原生 Tooltip 浮動提示 (商用無Emoji精簡版)
    """
    import calendar
    cal = calendar.Calendar(calendar.SUNDAY)
    month_days = cal.monthdayscalendar(year, month)
    
    # 星期標頭
    headers = ["日", "一", "二", "三", "四", "五", "六"]
    header_html = "".join([f"<th style='text-align: center; font-weight: bold; background: #f0f2f6; padding: 6px; border: 1px solid #e6e9ef;'>{h}</th>" for h in headers])
    
    rows_html = []
    for week in month_days:
        row_cells = []
        for day in week:
            if day == 0:
                row_cells.append("<td style='border: 1px solid #e6e9ef; height: 45px;'></td>")
            else:
                target_date = datetime(year, month, day).date()
                day_events = events.get(target_date, [])
                
                cell_style = "border: 1px solid #e6e9ef; height: 45px; text-align: center; vertical-align: middle; font-size: 14px;"
                
                if day_events:
                    # 使用 HTML 實體 &#13; 實現 Tooltip 多行換行顯示 (移除 Emoji，保持簡潔商用風格)
                    tooltip_text = f"除息預告 ({year}/{month:02d}/{day:02d})：&#13;" + "&#13;".join([f"{ev['code']} {ev['name']}: {ev['amount']}" for ev in day_events])
                    row_cells.append(
                        f"<td style='{cell_style} background-color: #ffcccc; color: #cc0000; font-weight: bold; cursor: pointer;' "
                        f"title='{tooltip_text}'>{day}</td>"
                    )
                else:
                    now_tw = datetime.now(timezone(timedelta(hours=8))).date()
                    if target_date == now_tw:
                        row_cells.append(f"<td style='{cell_style} background-color: #007bff; color: white; font-weight: bold;'>{day}</td>")
                    else:
                        row_cells.append(f"<td style='{cell_style}'>{day}</td>")
        rows_html.append(f"<tr>{''.join(row_cells)}</tr>")
        
    html_table = f"""
    <table style='width: 100%; border-collapse: collapse; font-family: sans-serif;'>
        <thead><tr>{header_html}</tr></thead>
        <tbody>{''.join(rows_html)}</tbody>
    </table>
    """
    return html_table

# ==================== 雅虎財報 EPS 欄位模糊相容性解析器 ====================
def get_eps_from_stmt(stmt):
    """
    自動適應雅虎財報在不同時期、不同個股所回傳的 EPS 欄位鍵名
    """
    if stmt is None or stmt.empty:
        return None
    # 遍歷常見的雅虎財報 EPS 欄位名稱
    for key in ['Basic EPS', 'Diluted EPS', 'BasicEarningsPerShare', 'DilutedEarningsPerShare', 'Basic', 'Diluted']:
        if key in stmt.index:
            return stmt.loc[key]
    # 模糊比對
    for idx in stmt.index:
        if "EPS" in str(idx) or "Earnings Per Share" in str(idx):
            return stmt.loc[idx]
    return None

def get_quarter_str(date_obj):
    """
    將財報日期轉換為季度標記字串，例如 2025Q3 [2]
    """
    try:
        dt = pd.to_datetime(date_obj)
        q = (dt.month - 1) // 3 + 1
        return f"{dt.year}Q{q}"
    except:
        return ""

# ==================== 側邊欄網站人氣統計看板 (商用無Emoji簡潔版) ====================
st.sidebar.markdown("<h3 style='text-align: center; font-weight: bold;'>網站數據統計</h3>", unsafe_allow_html=True)

# 雲端永久人氣計數器 (使用 hitscounter.dev 提供永久累積與更新，網址經由 URL 編碼確保唯一性)
visitor_badge_url = "https://hitscounter.dev/api/hit?url=https%3A%2F%2Fgithub.com%2Fgrace120429%2Fmy-stock-web&label=Total%20Views&color=%23007bff"

st.sidebar.markdown(
    f"""
    <div style='text-align: center; margin-bottom: 20px;'>
        <img src='{visitor_badge_url}' alt='Views'/>
    </div>
    """, 
    unsafe_allow_html=True
)

st.sidebar.markdown(
    """
    <div style='text-align: center; color: gray; font-size: 11px;'>
        提示：本計數器由雲端數據庫提供永久累計，每一次頁面載入皆會即時更新。
    </div>
    """,
    unsafe_allow_html=True
)

# ==================== 頁首資訊 ====================
st.title("台股三大法人飆股選股工具 by Kelly")

# 載入即時台幣匯率與集保資料日期
twd_str = data_fetcher.fetch_twd_data()
st.info(f"{twd_str}")

# ==================== 建立五大分頁 ====================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "三大法人選股大數據", 
    "我的自選監控", 
    "主力券商進出", 
    "台灣熱門 ETF 配息專區",
    "讀者交流留言區"
])

# ==================== 【分頁一：三大法人選股大數據】 ====================
with tab1:
    st.subheader("核心篩選與指標過濾")
    
    # 用 columns 將設定元件橫向排開，類似原 Tkinter 的排版
    col_cfg1, col_cfg2, col_cfg3 = st.columns([1, 2.2, 2.2])
    
    with col_cfg1:
        days_count = st.selectbox("籌碼區間：", [1, 3, 5, 7, 30, 60, 120], index=1, key="tab1_days")
        
    with col_cfg2:
        st.write("核心籌碼與信用篩選：")
        col_m1, col_m2, col_m3, col_m4, col_m5, col_m6, col_m7 = st.columns(7)
        f_active = col_m1.checkbox("外資", value=True)
        t_active = col_m2.checkbox("投信", value=False)
        d_active = col_m3.checkbox("自營商", value=True)
        m_active = col_m4.checkbox("融資 (資增)", value=True)
        m_balance_active = col_m5.checkbox("融資 (餘額最高)", value=False)  # 全市場融資最大量排行選項
        eps_surge_active = col_m6.checkbox("EPS 暴增", value=False)  # 核心選股
        b_active = col_m7.checkbox("分點券商", value=False)
        
        # 動態載入自訂分點下拉選單
        brokers_dict = storage.load_custom_brokers()
        selected_broker_name = st.selectbox("選定主力分點：", list(brokers_dict.keys()), index=0)

    with col_cfg3:
        st.write("指標進階過濾：")
        col_f1, col_f2, col_f3 = st.columns(3)
        filter_ma = col_f1.checkbox("日線多頭排列", value=True)
        filter_macd = col_f2.checkbox("日線 MACD金叉", value=True)
        filter_rev = col_f3.checkbox("月營收雙增", value=False)
        filter_vol = st.checkbox("量能突破 (爆量 2x)", value=True)

    # 執行篩選
    if st.button("開始一鍵篩選股票", type="primary", key="btn_run_tab1"):
        with st.spinner("正在進行大數據分析，請稍候..."):
            # 1. 抓取三大法人數據
            dfs, t86_dates = data_fetcher.get_recent_data(days_count=days_count)
            if not dfs:
                st.error("無法自證交所取得資料。")
            else:
                raw_data = pd.concat(dfs, ignore_index=True)
                
                # 2. 獲取集保大戶資料
                tdcc_raw, tdcc_date = data_fetcher.fetch_tdcc_data()
                if tdcc_raw and tdcc_date:
                    tdcc_ratios, tdcc_changes, _ = storage.save_and_get_tdcc_change(tdcc_raw, tdcc_date)
                else:
                    tdcc_ratios, tdcc_changes = {}, {}
                
                # 3. 背景獲取最新一期融資數據
                latest_date_str = sorted(t86_dates)[-1] if t86_dates else ""
                margin_data = data_fetcher.fetch_all_margin(latest_date_str) if latest_date_str else {}
                
                # 4. 下載月營收
                revenue_data = data_fetcher.fetch_monthly_revenue()
                
                # 5. 如果勾選分點券商，下載特定券商資料
                tab1_broker_data = {}
                if b_active:
                    broker_id = brokers_dict.get(selected_broker_name)
                    if broker_id:
                        days_param = 5 if days_count <= 7 else 20
                        tab1_broker_data = data_fetcher.fetch_broker_net_buys(broker_id, days_param)

                # --- 篩選與計算邏輯 ---
                combined = raw_data.copy()
                combined = combined[combined['證券代號'].str.match(r'^[a-zA-Z0-9]{4,6}$')]
                
                # 復原原本最完整的欄位備用匹配演算法
                col_foreign, col_trust, col_dealer = None, None, None
                for c in combined.columns:
                    if "外陸資買賣超股數(不含外資自營商)" == c: col_foreign = c
                    elif "投信買賣超股數" == c: col_trust = c
                    elif "自營商買賣超股數" == c: col_dealer = c
                    
                if not col_foreign:
                    for c in combined.columns:
                        if "外陸資買賣超股數" in c or "外資買賣超股數" in c:
                            col_foreign = c
                            break
                if not col_trust:
                    for c in combined.columns:
                        if "投信買賣超" in c:
                            col_trust = c
                            break
                if not col_dealer:
                    for c in combined.columns:
                        if "自營商買賣超股數" in c and "自行買賣" not in c and "避險" not in c:
                            col_dealer = c
                            break
                
                def to_num(val):
                    try: return float(str(val).replace(',', ''))
                    except: return 0.0
                
                if col_foreign: combined[col_foreign] = combined[col_foreign].apply(to_num)
                if col_trust: combined[col_trust] = combined[col_trust].apply(to_num)
                if col_dealer: combined[col_dealer] = combined[col_dealer].apply(to_num)
                
                summary = combined.groupby(['證券代號', '證券名稱']).agg({
                    col_foreign: 'sum' if col_foreign else 'max',
                    col_trust: 'sum' if col_trust else 'max',
                    col_dealer: 'sum' if col_dealer else 'max'
                }).reset_index()
                
                summary['外資_張'] = summary[col_foreign] / 1000 if col_foreign else 0
                summary['投信_張'] = summary[col_trust] / 1000 if col_trust else 0
                summary['自營_張'] = summary[col_dealer] / 1000 if col_dealer else 0
                summary['融資_張'] = summary['證券代號'].apply(lambda c: margin_data.get(c, {}).get("change", 0.0))
                summary['融資_餘額'] = summary['證券代號'].apply(lambda c: margin_data.get(c, {}).get("today", 0.0))  # 映射融資總餘額
                summary['分點_萬'] = summary['證券代號'].apply(lambda c: tab1_broker_data.get(c, {}).get("diff", 0.0) if b_active else 0.0)
                
                filtered_summary = summary.copy()
                filtered_summary['排序得分'] = 0.0
                
                # 安全阻攔機制
                if not (f_active or t_active or d_active or m_active or m_balance_active or eps_surge_active or b_active):
                    st.warning("請至少勾選一個核心篩選指標！")
                else:
                    if f_active:
                        filtered_summary = filtered_summary[filtered_summary['外資_張'] > 0]
                        filtered_summary['排序得分'] += filtered_summary['外資_張']
                    if t_active:
                        filtered_summary = filtered_summary[filtered_summary['投信_張'] > 0]
                        filtered_summary['排序得分'] += filtered_summary['投信_張']
                    if d_active:
                        filtered_summary = filtered_summary[filtered_summary['自營_張'] > 0]
                        filtered_summary['排序得分'] += filtered_summary['自營_張']
                    if m_active:
                        filtered_summary = filtered_summary[filtered_summary['融資_張'] > 0]
                        filtered_summary['排序得分'] += filtered_summary['融資_張']
                    if m_balance_active:
                        filtered_summary = filtered_summary[filtered_summary['融資_餘額'] > 0]
                        filtered_summary['排序得分'] += filtered_summary['融資_餘額'] / 10.0  # 同位加權
                    if b_active:
                        filtered_summary = filtered_summary[filtered_summary['分點_萬'] > 0]
                        filtered_summary['排序得分'] += filtered_summary['分點_萬'] / 10.0
                    
                    # 核心選股：如果「完全不勾三大法人與信用融資」，只勾選「EPS 暴增」進行獨立選股
                    if eps_surge_active and not (f_active or t_active or d_active or m_active or m_balance_active or b_active):
                        filtered_summary['排序得分'] = (
                            filtered_summary[col_foreign].abs() / 1000 + 
                            filtered_summary[col_trust].abs() / 1000 + 
                            filtered_summary[col_dealer].abs() / 1000 + 
                            filtered_summary['融資_餘額'] / 10.0
                        )
                        top_candidates = filtered_summary.sort_values(by='排序得分', ascending=False).head(80)
                    else:
                        top_candidates = filtered_summary.sort_values(by='排序得分', ascending=False).head(50)
                    
                    # 逐檔 analysis 多週期與技術面指標
                    final_rows = []
                    errors_log = []  # 收集下載錯誤用
                    
                    # 建立安全獨立的 yf_session
                    yf_session = create_yf_session()
                    
                    for _, row_item in top_candidates.iterrows():
                        code = row_item['證券代號']
                        name = row_item['證券名稱']
                        ticker = f"{code}.TW"
                        
                        # 營收篩選
                        rev_item = revenue_data.get(code)
                        if filter_rev:
                            if not rev_item or rev_item.get("yoy", 0) <= 0 or rev_item.get("mom", 0) <= 0:
                                continue
                        
                        # 智慧型提示初始化
                        is_code_etf = (len(code) >= 5) or (len(code) == 4 and code.startswith("00"))
                        
                        # 智慧過濾：如果啟用了「EPS 暴增」核心選股，而個股是 ETF，直接淘汰跳過（省去下載財報時間）
                        if eps_surge_active and is_code_etf:
                            continue
                        
                        latest_q_eps_val = "ETF無EPS" if is_code_etf else "載入中..."
                        latest_a_eps_val = "ETF無EPS" if is_code_etf else "載入中..."
                        
                        try:
                            time.sleep(0.15)  # 禮貌防阻擋安全等待
                            
                            # 無條件建立 stock 對象 (解決在快取讀取時變數 undefined 崩潰)
                            stock = yf.Ticker(ticker, session=yf_session)
                            
                            # 使用 Session State 做為 K 線資料快取
                            if ticker in st.session_state.yf_cache:
                                hist = st.session_state.yf_cache[ticker]
                            else:
                                hist = stock.history(period="6mo")
                                if not hist.empty and len(hist) >= 20:
                                    st.session_state.yf_cache[ticker] = hist
                            
                            if hist.empty or len(hist) < 20:
                                errors_log.append(f"{code}: 歷史數據不足")
                                continue
                                
                            # 核心修改：不論有沒有勾選過濾，只要是非 ETF 股票，一律下載並顯示真實的 EPS 數據！
                            if not is_code_etf:
                                try:
                                    q_stmt = stock.quarterly_income_stmt
                                    a_stmt = stock.income_stmt
                                except:
                                    q_stmt = stock.quarterly_financials
                                    a_stmt = stock.financials
                                q_eps_series = get_eps_from_stmt(q_stmt)
                                a_eps_series = get_eps_from_stmt(a_stmt)
                                if q_eps_series is not None and not q_eps_series.empty and a_eps_series is not None and not a_eps_series.empty:
                                    latest_q_eps = q_eps_series.iloc[0]
                                    
                                    # 計算最新單季所在的季度標記 (例如 2025Q3) [2]
                                    q_date = q_eps_series.index[0]
                                    q_str = get_quarter_str(q_date)
                                    
                                    # 抓取「去年年度EPS」（例如當前為 2026 年，則主動抓取並顯示 2025 年）[2]
                                    target_year = datetime.now(timezone(timedelta(hours=8))).year - 1
                                    a_eps_val = None
                                    a_eps_year = None
                                    for idx_date, val in a_eps_series.items():
                                        try:
                                            dt = pd.to_datetime(idx_date)
                                            if dt.year == target_year:
                                                a_eps_val = val
                                                a_eps_year = target_year
                                                break
                                        except:
                                            pass
                                    # 備用方案：若去年年報未發布，則採用第一筆(最新一筆)年報資料
                                    if a_eps_val is None:
                                        try:
                                            first_date = a_eps_series.index[0]
                                            dt = pd.to_datetime(first_date)
                                            a_eps_val = a_eps_series.iloc[0]
                                            a_eps_year = dt.year
                                        except:
                                            pass
                                    
                                    if pd.notna(latest_q_eps) and a_eps_val is not None and pd.notna(a_eps_val):
                                        latest_q_eps_val = f"({q_str}) {round(latest_q_eps, 2)} 元" if q_str else f"{round(latest_q_eps, 2)} 元"
                                        latest_a_eps_val = f"({a_eps_year}年) {round(a_eps_val, 2)} 元"
                                        
                                        # 核心過濾：如果啟用了「EPS 暴增」核心選股，而個股「季 EPS <= 最新年報 EPS」，則直接淘汰
                                        latest_a_eps = a_eps_series.iloc[0]
                                        if eps_surge_active and latest_q_eps <= latest_a_eps:
                                            continue
                                    else:
                                        if eps_surge_active:
                                            continue  # 數據缺值，淘汰
                                else:
                                    if eps_surge_active:
                                        continue  # 財報無資訊，淘汰
                                
                            # 計算均線
                            hist['MA5'] = hist['Close'].rolling(5).mean()
                            hist['MA20'] = hist['Close'].rolling(20).mean()
                            latest = hist.iloc[-1]
                            
                            price = latest['Close']
                            ma5 = latest['MA5']
                            ma20 = latest['MA20']
                            
                            # 量能突破計算
                            latest_vol = latest['Volume']
                            prev_20d_avg_vol = hist['Volume'].iloc[-21:-1].mean()
                            vol_ratio = latest_vol / prev_20d_avg_vol if prev_20d_avg_vol > 0 else 0.0
                            if filter_vol and vol_ratio < 2.0:
                                continue
                                
                            is_bullish = (price > ma5) and (price > ma20) and (ma5 > ma20)
                            ma_status = "均線向上" if is_bullish else "整理/向下"  # 商用版：移除表情符號
                            if filter_ma and not is_bullish:
                                continue
                                
                            # 量能格式化
                            vol_status_str = f"量增 {vol_ratio:.1f}x" if vol_ratio >= 1.0 else f"量縮 {vol_ratio:.1f}x"
                            ma_status_display = f"{ma_status} ({vol_status_str})"
                            
                            # MACD 計算 (台股常規：空頭時以綠色 🟢 表示警告，多頭時以紅色 🔴 表示)
                            latest_osc_daily, prev_osc_daily = helpers.calculate_macd(hist['Close'])
                            raw_macd_daily = helpers.get_macd_status_str(latest_osc_daily, prev_osc_daily).replace("🟢 ", "").replace("🔴 ", "")
                            
                            if latest_osc_daily is not None and latest_osc_daily <= 0:
                                macd_daily_status = f"🟢 {raw_macd_daily}"
                            else:
                                macd_daily_status = f"🔴 {raw_macd_daily}"
                            
                            if filter_macd and "MACD金叉" not in macd_daily_status and "多頭" not in macd_daily_status:
                                continue
                                
                            # 60分K MACD (同樣依台股常規套用 🟢/🔴 色彩標誌)
                            try:
                                if ticker in st.session_state.yf_60m_cache:
                                    hist_60m = st.session_state.yf_60m_cache[ticker]
                                else:
                                    stock_60m = yf.Ticker(ticker, session=yf_session)
                                    hist_60m = stock_60m.history(interval="60m", period="1mo")
                                    if not hist_60m.empty:
                                        st.session_state.yf_60m_cache[ticker] = hist_60m
                                latest_osc_60m, prev_osc_60m = helpers.calculate_macd(hist_60m['Close'])
                                raw_macd_60m = helpers.get_macd_status_str(latest_osc_60m, prev_osc_60m).replace("🟢 ", "").replace("🔴 ", "")
                                
                                if latest_osc_60m is not None and latest_osc_60m <= 0:
                                    macd_60m_status = f"🟢 {raw_macd_60m}"
                                else:
                                    macd_60m_status = f"🔴 {raw_macd_60m}"
                            except:
                                macd_60m_status = "N/A"
                                
                            # 支撐壓力點
                            sr_1m, sr_6m = helpers.get_dynamic_sr(hist, price)
                            
                            prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else price
                            pct_change = ((price - prev_price) / prev_price) * 100
                            
                            # 👈 核心重整：依照關聯性重新組合欄位順序 (代號 -> 名稱 -> 價格 -> EPS -> 營收 -> 三大法人 -> 融資與籌碼大戶 -> 技術指標)
                            final_rows.append({
                                "代號": code,
                                "股票名稱": name,
                                "收盤價": round(price, 1),
                                "漲跌幅(%)": round(pct_change, 2),
                                "最新單季EPS": latest_q_eps_val,
                                "去年年度EPS": latest_a_eps_val,  # 👈 修正為去年年度EPS [2]
                                "月營收YoY/MoM": helpers.format_rev_growth(rev_item),  # 👈 營收緊貼放在年度EPS後面
                                "外資金額(萬)": round(row_item['外資_張'] * price / 10, 1),
                                "投信金額(萬)": round(row_item['投信_張'] * price / 10, 1),
                                "自營金額(萬)": round(row_item['自營_張'] * price / 10, 1),
                                "融資餘額(張)": int(margin_data.get(code, {}).get("today", 0.0)),  # 👈 融資餘額移到自營金額後面
                                "融資變動(張)": int(summary.loc[summary['證券代號'] == code, '融資_張'].values[0]),  # 👈 融資變動緊貼在餘額後面
                                "大戶比例": f"{round(tdcc_ratios.get(code, 0), 2)}%" if code in tdcc_ratios else "N/A",  # 👈 大戶比例緊貼放在融資後面
                                "均線狀態": ma_status_display,
                                "日K_MACD": macd_daily_status,
                                "60m_MACD": macd_60m_status,
                                "短期支壓(1M)": sr_1m,
                                "中期支壓(6M)": sr_6m,
                                "K線圖網址": f"https://tw.stock.yahoo.com/quote/{code}/technical-analysis"
                            })
                        except Exception as ex:
                            errors_log.append(f"{code}: {str(ex)}")
                            continue
                            
                    if final_rows:
                        df_res = pd.DataFrame(final_rows)
                        st.success(f"篩選完成！共尋獲 {len(df_res)} 檔符合條件個股。")
                        
                        st.dataframe(
                            df_res, 
                            column_config={
                                "K線圖網址": st.column_config.LinkColumn("看日K線圖", display_text="開啟奇摩股市")
                            },
                            use_container_width=True
                        )
                    else:
                        st.warning("無符合當前篩選與過濾條件之個個股，請放寬條件再試。")
                        if errors_log:
                            with st.expander("⚠️ 查看背景連線診斷報告"):
                                st.write(errors_log[:10])

# ==================== 【分頁二：我的自選監控】 ====================
with tab2:
    st.subheader("觀察名單即時監控")
    
    # 載入自選監控
    watchlist = storage.load_watchlist()
    
    col_w1, col_w2 = st.columns([1, 3])
    with col_w1:
        st.write("自選股管理")
        new_watchlist_code = st.text_input("輸入股票代號加入自選：", max_chars=6, key="add_w")
        if st.button("加入自選清單"):  # 商用版：移除表情符號
            if new_watchlist_code:
                new_watchlist_code = new_watchlist_code.strip()
                if new_watchlist_code not in watchlist:
                    watchlist.append(new_watchlist_code)
                    storage.save_watchlist(watchlist)
                    st.success(f"已成功新增自選股 {new_watchlist_code}！")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.info(f"股票代號 {new_watchlist_code} 已存在於自選名單中。")
                    
        del_watchlist_code = st.text_input("輸入股票代號移除自選：", max_chars=6, key="del_w")
        if st.button("移除自選項目", type="secondary"):  # 商用版：移除表情符號
            del_watchlist_code = del_watchlist_code.strip()
            if del_watchlist_code in watchlist:
                watchlist.remove(del_watchlist_code)
                storage.save_watchlist(watchlist)
                st.success(f"已成功移除自選股 {del_watchlist_code}！")
                time.sleep(0.5)
                st.rerun()
            else:
                st.warning(f"自選名單中找不到 {del_watchlist_code}。")
        
        st.write("---")
        st.write("目前監控中的股票代號：")
        if watchlist:
            st.info(", ".join(watchlist))
        else:
            st.warning("目前監控清單為空。")

    with col_w2:
        st.write("自選股雙週期趨勢與警示看板")
        
        if watchlist:
            if st.button("手動重新整理自選數據"):  # 商用版：移除表情符號
                st.session_state.yf_cache.clear()
                st.session_state.yf_60m_cache.clear()
                st.success("快取已清除，正在重新抓取...")
                time.sleep(0.5)
                st.rerun()
                
            w_rows = []
            errors_log_tab2 = []
            
            # 建立線程安全獨立 Session
            yf_session_tab2 = create_yf_session()
            
            with st.spinner("正在分析自選股趨勢與支撐壓力點，請稍候..."):
                revenue_data = data_fetcher.fetch_monthly_revenue()
                tdcc_raw, tdcc_date = data_fetcher.fetch_tdcc_data()
                tdcc_ratios, tdcc_changes = {}, {}
                if tdcc_raw and tdcc_date:
                    tdcc_ratios, tdcc_changes, _ = storage.save_and_get_tdcc_change(tdcc_raw, tdcc_date)
                    
                for code in watchlist:
                    ticker = f"{code}.TW"
                    name = data_fetcher.fetch_stock_name_fast(code)
                    
                    # 智慧型提示初始化 (分頁二同步支援)
                    is_code_etf_tab2 = (len(code) >= 5) or (len(code) == 4 and code.startswith("00"))
                    latest_q_eps_val_tab2 = "ETF無EPS" if is_code_etf_tab2 else "載入中..."
                    latest_a_eps_val_tab2 = "ETF無EPS" if is_code_etf_tab2 else "載入中..."
                    
                    try:
                        time.sleep(0.15)  # 安全等待
                        
                        stock = yf.Ticker(ticker, session=yf_session_tab2)
                        hist = stock.history(period="6mo")
                        if hist.empty:
                            ticker = f"{code}.TWO"
                            stock = yf.Ticker(ticker, session=yf_session_tab2)
                            hist = stock.history(period="6mo")
                        
                        if hist.empty or len(hist) < 20:
                            errors_log_tab2.append(f"{code}: 歷史K線數據不足")
                            continue
                            
                        # 分頁二（自選監控）自動載入最新年度與單季 EPS 數據
                        if not is_code_etf_tab2:
                            try:
                                try:
                                    q_stmt = stock.quarterly_income_stmt
                                    a_stmt = stock.income_stmt
                                except:
                                    q_stmt = stock.quarterly_financials
                                    a_stmt = stock.financials
                                q_eps_series = get_eps_from_stmt(q_stmt)
                                a_eps_series = get_eps_from_stmt(a_stmt)
                                if q_eps_series is not None and not q_eps_series.empty and a_eps_series is not None and not a_eps_series.empty:
                                    latest_q_eps = q_eps_series.iloc[0]
                                    
                                    # 計算最新單季所在的季度標記 (例如 2025Q3) [2]
                                    q_date = q_eps_series.index[0]
                                    q_str = get_quarter_str(q_date)
                                    
                                    # 抓取「去年年度EPS」 (例如當前為 2026 年，則主動抓取並顯示 2025 年) [2]
                                    target_year = datetime.now(timezone(timedelta(hours=8))).year - 1
                                    a_eps_val = None
                                    a_eps_year = None
                                    for idx_date, val in a_eps_series.items():
                                        try:
                                            dt = pd.to_datetime(idx_date)
                                            if dt.year == target_year:
                                                a_eps_val = val
                                                a_eps_year = target_year
                                                break
                                        except:
                                            pass
                                    if a_eps_val is None:
                                        try:
                                            first_date = a_eps_series.index[0]
                                            dt = pd.to_datetime(first_date)
                                            a_eps_val = a_eps_series.iloc[0]
                                            a_eps_year = dt.year
                                        except:
                                            pass
                                    
                                    if pd.notna(latest_q_eps) and a_eps_val is not None and pd.notna(a_eps_val):
                                        latest_q_eps_val_tab2 = f"({q_str}) {round(latest_q_eps, 2)} 元" if q_str else f"{round(latest_q_eps, 2)} 元"
                                        latest_a_eps_val_tab2 = f"({a_eps_year}年) {round(a_eps_val, 2)} 元"
                                    else:
                                        latest_q_eps_val_tab2 = "N/A"
                                        latest_a_eps_val_tab2 = "N/A"
                                else:
                                    latest_q_eps_val_tab2 = "N/A"
                                    latest_a_eps_val_tab2 = "N/A"
                            except:
                                latest_q_eps_val_tab2 = "N/A"
                                latest_a_eps_val_tab2 = "N/A"
                                
                        price = hist['Close'].iloc[-1]
                        prev_price = hist['Close'].iloc[-2]
                        pct_change = ((price - prev_price) / prev_price) * 100
                        
                        # MACD 與警示 (依台股常規調整色彩：空頭🟢，多頭🔴)
                        latest_osc_daily, prev_osc_daily = helpers.calculate_macd(hist['Close'])
                        raw_macd_daily = helpers.get_macd_status_str(latest_osc_daily, prev_osc_daily).replace("🟢 ", "").replace("🔴 ", "")
                        
                        if latest_osc_daily is not None and latest_osc_daily <= 0:
                            macd_daily_status = f"🟢 {raw_macd_daily}"
                        else:
                            macd_daily_status = f"🔴 {raw_macd_daily}"
                        
                        # 60m MACD (同樣依台股常規套用🟢/🔴)
                        try:
                            stock_60m = yf.Ticker(ticker, session=yf_session_tab2)
                            hist_60m = stock_60m.history(interval="60m", period="1mo")
                            latest_osc_60m, prev_osc_60m = helpers.calculate_macd(hist_60m['Close'])
                            raw_macd_60m = helpers.get_macd_status_str(latest_osc_60m, prev_osc_60m).replace("🟢 ", "").replace("🔴 ", "")
                            
                            if latest_osc_60m is not None and latest_osc_60m <= 0:
                                macd_60m_status = f"🟢 {raw_macd_60m}"
                            else:
                                macd_60m_status = f"🔴 {raw_macd_60m}"
                        except:
                            macd_60m_status = "N/A"
                            latest_osc_60m = None
                            
                        is_daily_bear = (latest_osc_daily is not None and latest_osc_daily <= 0)
                        is_60m_bear = (latest_osc_60m is not None and latest_osc_60m <= 0)
                        if is_daily_bear and is_60m_bear:
                            alert_str = "🟢 賣出警示 (MACD雙空)"
                        elif is_daily_bear and not is_60m_bear:
                            alert_str = "🟡 先驅起漲 (日空/短轉強)"
                        elif not is_daily_bear and is_60m_bear:
                            alert_str = "🟡 短線修正 (日多/短轉弱)"
                        else:
                            alert_str = "🔴 趨勢強勢 (MACD雙多)"
                        
                        # 自選股同步運算量能突破，並拼接進狀態欄
                        latest_vol = hist['Volume'].iloc[-1]
                        prev_20d_avg_vol = hist['Volume'].iloc[-21:-1].mean()
                        vol_ratio = latest_vol / prev_20d_avg_vol if prev_20d_avg_vol > 0 else 0.0
                        vol_status_str = f"量增 {vol_ratio:.1f}x" if vol_ratio >= 1.0 else f"量縮 {vol_ratio:.1f}x"
                        alert_str_display = f"{alert_str} ({vol_status_str})"
                            
                        sr_1m, sr_6m = helpers.get_dynamic_sr(hist, price)
                        
                        # 👈 核心重整：分頁二（自選監控）比照關聯性優化順序 (代號 -> 名稱 -> 價格 -> EPS -> 營收 -> 籌碼大戶 -> 技術指標)
                        w_rows.append({
                            "代號": code,
                            "股票名稱": name,
                            "現價": round(price, 1),
                            "漲跌幅(%)": round(pct_change, 2),
                            "最新單季EPS": latest_q_eps_val_tab2,  # 👈 EPS 數據
                            "去年年度EPS": latest_a_eps_val_tab2,  # 👈 修正為去年年度EPS [2]
                            "月營收YoY/MoM": helpers.format_rev_growth(revenue_data.get(code)),  # 👈 營收緊貼放在EPS後面
                            "大戶比例": f"{round(tdcc_ratios.get(code, 0), 2)}%" if code in tdcc_ratios else "N/A",  # 👈 大戶比例緊貼放在營收後面
                            "日K_MACD": macd_daily_status,
                            "60分K_MACD": macd_60m_status,
                            "趨勢狀態": alert_str_display,
                            "短期支壓(1M)": sr_1m,
                            "中期支壓(6M)": sr_6m
                        })
                    except Exception as ex_tab2:
                        errors_log_tab2.append(f"{code}: {str(ex_tab2)}")
                        continue
                        
            if w_rows:
                st.dataframe(pd.DataFrame(w_rows), use_container_width=True)
            else:
                st.warning("自選股數據分析失敗，請查看下方診斷報告。")
                
            if errors_log_tab2:
                with st.expander("⚠️ 查看自選背景診斷報告"):
                    st.write(errors_log_tab2)
        else:
            st.info("目前自選觀察名單為空。請在左側輸入股票代碼並點擊加入，系統將會自動為您監控趨勢！")

# ==================== 【分頁三：主力券商進出】 ====================
with tab3:
    st.subheader("特寫分點主力特定天數交易明細")
    
    # 自訂分點管理介面
    with st.expander("管理我的自訂券商分點"):  # 商用版：移除表情符號
        col_b1, col_b2 = st.columns(2)
        new_b_name = col_b1.text_input("分點名稱 (如: 凱基台北)：")
        new_b_code = col_b2.text_input("分點代號 (4碼，如: 9268)：")
        if st.button("儲存新分點"):  # 商用版：移除表情符號
            if new_b_name and new_b_code:
                brokers_dict[new_b_name] = new_b_code.lower()
                storage.save_custom_brokers(brokers_dict)
                st.success(f"已儲存：{new_b_name} ({new_b_code})")
                st.rerun()
                
    col_q1, col_q2, col_q3 = st.columns(3)
    target_broker = col_q1.selectbox("選擇統計主力分點：", list(brokers_dict.keys()), key="broker_tab3")
    target_days = col_q2.selectbox("統計天數：", ["近1日", "近5日", "近10日", "近20日"], index=1)
    target_filter = col_q3.selectbox("過濾進出方向：", ["全部進出", "僅顯示買超", "僅顯示賣超"])
    
    if st.button("開始查詢主力買賣超"):  # 商用版：移除表情符號
        days_map = {"近1日": 1, "近5日": 5, "近10日": 10, "近20日": 20}
        days_param = days_map.get(target_days, 5)
        b_id = brokers_dict.get(target_broker)
        
        with st.spinner("下載主力券商進出明細中..."):
            broker_results = data_fetcher.fetch_broker_net_buys(b_id, days_param)
            if broker_results:
                b_rows = []
                for b_code, item in broker_results.items():
                    diff = item["diff"]
                    if target_filter == "僅顯示買超" and diff <= 0: continue
                    if target_filter == "僅顯示賣超" and diff >= 0: continue
                    
                    b_rows.append({
                        "代號": b_code,
                        "股票名稱": item["name"],
                        "買進金額(萬)": item["buy"],
                        "賣出金額(萬)": item["sell"],
                        "淨買超(萬)": diff,
                        "進出方向": "淨買超" if diff > 0 else "淨賣超"  # 商用版：移除表情符號
                    })
                if b_rows:
                    df_b = pd.DataFrame(b_rows).sort_values(by="淨買超(萬)", key=abs, ascending=False)
                    st.dataframe(df_b, use_container_width=True)
                else:
                    st.info("所選條件下無進出明細。")
            else:
                st.error("無法自券商系統獲取資料，請稍後重試。")

# ==================== 【分頁四：台灣熱門 ETF 配息與退休存錢筒】 ====================
with tab4:
    # 初始化日曆日期與事件儲存結構
    now_tw = datetime.now(timezone(timedelta(hours=8)))
    if "cal_year" not in st.session_state:
        st.session_state.cal_year = now_tw.year
    if "cal_month" not in st.session_state:
        st.session_state.cal_month = now_tw.month
    if "etf_events" not in st.session_state:
        st.session_state.etf_events = {}

    st.subheader("熱門與主動式 ETF 動態息收與殖利率看板")
    
    # 讀取 ETF 清單
    hot_etfs = storage.load_custom_etfs()
    
    # 建立左右兩欄佈局：左邊為 ETF 表格，右邊為除息日曆 (還原 Tkinter 右側面板排版)
    col_main_left, col_main_right = st.columns([3, 1.2])
    
    with col_main_left:
        col_e1, col_e2 = st.columns([1, 2])
        with col_e1:
            new_etf_code = st.text_input("新增自選 ETF (代碼)：", max_chars=6, key="add_etf_code")
            if st.button("新增 ETF"):  # 商用版：移除表情符號
                if new_etf_code:
                    new_etf_code = new_etf_code.upper().strip()
                    etf_name = data_fetcher.fetch_stock_name_fast(new_etf_code)
                    if etf_name == "未知":
                        etf_name = f"自訂 ETF {new_etf_code}"
                    
                    if not any(item[0] == new_etf_code for item in hot_etfs):
                        hot_etfs.append((new_etf_code, etf_name))
                        storage.save_custom_etfs(hot_etfs)
                        st.success(f"已新增：{new_etf_code} {etf_name}")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.info(f"ETF {new_etf_code} 已經在您的清單中囉！")
                        
            del_etf_code = st.text_input("輸入要移除的 ETF 代碼：", max_chars=6, key="del_etf_code")
            if st.button("刪除選中 ETF", type="secondary"):  # 商用版：移除表情符號
                if del_etf_code:
                    del_etf_code = del_etf_code.upper().strip()
                    if any(item[0] == del_etf_code for item in hot_etfs):
                        hot_etfs = [item for item in hot_etfs if item[0] != del_etf_code]
                        storage.save_custom_etfs(hot_etfs)
                        st.success(f"已成功刪除：{del_etf_code}")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.warning(f"在您的清單中找不到 ETF 代碼 {del_etf_code}，無法刪除。")
                
        with col_e2:
            st.write("最新預估配息與收益清單：")
            upcoming_dict = data_fetcher.fetch_upcoming_dividends()
            etf_rows = []
            
            # 使用線程安全的 Session
            yf_session_tab4 = create_yf_session()
            
            # 清空本次執年的日曆事件快取，準備重新收集
            st.session_state.etf_events = {}
            
            for code, name in hot_etfs:
                data = data_fetcher.fetch_etf_dividend_details(code, upcoming_dict)
                if data:
                    etf_rows.append({
                        "代號": code,
                        "ETF名稱": name,
                        "現價": round(data["price"], 2),
                        "配息頻率": data["frequency"],
                        "最新單期配息": data["last_amount"],
                        "除息交易日": data["ex_date"],
                        "年度累計配息": data["current_year_sum"],
                        "預估年化殖利率": data["yield"],
                        "除息提醒狀態": data["status"].replace("🔔 ", "").replace("🔴 ", "").replace("⏳ ", "")  # 👈 移除表情
                    })
                    
                    # 收集除息日期事件至行事曆快取中
                    ex_date_str = data.get("ex_date", "N/A")
                    last_amt_str = data.get("last_amount", "N/A")
                    if ex_date_str != "N/A" and "尚未公告" not in last_amt_str:
                        try:
                            ex_date_obj = datetime.strptime(ex_date_str, "%Y/%m/%d").date()
                            if ex_date_obj not in st.session_state.etf_events:
                                st.session_state.etf_events[ex_date_obj] = []
                            st.session_state.etf_events[ex_date_obj].append({
                                "code": code,
                                "name": name,
                                "amount": last_amt_str
                            })
                        except:
                            pass
            if etf_rows:
                st.dataframe(pd.DataFrame(etf_rows), use_container_width=True)
            else:
                st.info("目前無 ETF 息收數據。")

    with col_main_right:
        st.write("📅 ETF 除息行事曆")
        
        # 建立與 Tkinter 一致的左右導航按鈕與月份標題
        col_nav1, col_nav2, col_nav3 = st.columns([1, 2, 1])
        with col_nav1:
            if st.button("◀", key="prev_month"):
                st.session_state.cal_month -= 1
                if st.session_state.cal_month < 1:
                    st.session_state.cal_month = 12
                    st.session_state.cal_year -= 1
                st.rerun()
        with col_nav2:
            st.markdown(f"<h5 style='text-align: center; font-weight: bold;'>{st.session_state.cal_year} 年 {st.session_state.cal_month:02d} 月</h5>", unsafe_allow_html=True)
        with col_nav3:
            if st.button("▶", key="next_month"):
                st.session_state.cal_month += 1
                if st.session_state.cal_month > 12:
                    st.session_state.cal_month = 1
                    st.session_state.cal_year += 1
                st.rerun()
                
        # 渲染 HTML 行事曆
        html_cal = render_streamlit_calendar(
            st.session_state.cal_year, 
            st.session_state.cal_month, 
            st.session_state.etf_events
        )
        st.markdown(html_cal, unsafe_allow_html=True)
        st.caption("提示：滑鼠懸停在紅色的除息日期上，可觀看當天除息 ETF 與金額詳情。")

    # 退休配息存錢筒
    st.write("---")
    st.subheader("我的股息退休存錢筒 (複利配息計算機)")
    piggy_bank_data = storage.load_piggy_bank()
    
    col_p1, col_p2 = st.columns([1, 3])
    with col_p1:
        p_code = st.text_input("ETF 代號：", max_chars=6, key="pb_c")
        p_shares = st.number_input("持有張數：", min_value=0.1, step=0.5, format="%.1f")
        if st.button("更新持股"):  # 商用版：移除表情符號
            if p_code:
                p_code = p_code.upper().strip()
                piggy_bank_data[p_code] = p_shares
                storage.save_piggy_bank(piggy_bank_data)
                st.success(f"持股已更新：{p_code} {p_shares}張")
                time.sleep(0.5)
                st.rerun()
                
        p_del = st.text_input("要移除的代號：", max_chars=6, key="pb_del")
        if st.button("移除持股"):  # 商用版：移除表情符號
            p_del = p_del.upper().strip()
            if p_del in piggy_bank_data:
                del piggy_bank_data[p_del]
                storage.save_piggy_bank(piggy_bank_data)
                st.success(f"已移除持股：{p_del}")
                time.sleep(0.5)
                st.rerun()
                
    with col_p2:
        st.write("退休被動收入配息模擬清單：")
        pb_rows = []
        total_market_value = 0.0
        total_annual_dividend = 0.0
        total_selected_month_dividend = 0.0  # 該月份實際預估配息收入
        
        for code, shares in piggy_bank_data.items():
            data = data_fetcher.fetch_etf_dividend_details(code, upcoming_dict)
            if data:
                price = data["price"]
                current_year_sum_val = data.get("current_year_sum_val", 0.0)
                latest_div_value = data.get("latest_div_value", 0.0)
                ex_date_str = data.get("ex_date", "N/A")
                
                est_annual = shares * 1000 * current_year_sum_val
                market_val = shares * 1000 * price
                
                total_market_value += market_val
                total_annual_dividend += est_annual
                
                # 計算與行事曆連動的「該月份實際除息收入」
                ex_month = None
                ex_year = None
                try:
                    ex_date_obj = datetime.strptime(ex_date_str, "%Y/%m/%d")
                    ex_month = ex_date_obj.month
                    ex_year = ex_date_obj.year
                except:
                    pass
                    
                # 比對是否與日曆顯示的年月份相同
                if ex_month == st.session_state.cal_month and ex_year == st.session_state.cal_year:
                    total_selected_month_dividend += shares * 1000 * latest_div_value
                
                pb_rows.append({
                    "代號": code,
                    "持股張數": f"{shares} 張",
                    "現價": f"{round(price, 1)} 元",
                    "預估單股年配息": f"{current_year_sum_val} 元",
                    "預估年領股息": f"{int(est_annual):,} 元",
                    "持股市值": f"{int(market_val):,} 元"
                })
        if pb_rows:
            st.dataframe(pd.DataFrame(pb_rows), use_container_width=True)
            
            # 統計看板 (商用版：移除表情符號，並直接顯示指定月份的實質配息收入)
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            col_stat1.metric("總持股市值", f"{int(total_market_value):,} 元")
            col_stat2.metric("預估年領總股息", f"{int(total_annual_dividend):,} 元")
            col_stat3.metric(
                f"{st.session_state.cal_month}月份預估配息收入", 
                f"{int(total_selected_month_dividend):,} 元",
                delta="該月份實際配息收入" if total_selected_month_dividend > 0 else "本月份無除息"
            )
        else:
            st.info("存錢筒目前無持股，請新增您的 ETF 持股比例。")

# ==================== 【分頁五：讀者交流留言區】 ====================
with tab5:
    st.subheader("💬 讀者交流留言區")
    
    # 載入現有留言
    comments = load_comments()
    
    # 留言發表表單
    with st.form("comment_form", clear_on_submit=True):
        col_author, col_submit = st.columns([1, 3])
        author_name = col_author.text_input("您的稱呼：", max_chars=10, value="匿名讀者")
        comment_content = st.text_area("留言內容：", max_chars=200, placeholder="歡迎在這裡分享您的想法或回饋...")
        submitted = st.form_submit_with_button("送出留言")
        
        if submitted:
            if not comment_content.strip():
                st.warning("請填寫留言內容！")
            else:
                # 建立新留言資料
                new_comment = {
                    "id": int(time.time() * 1000),  # 以毫秒級時間戳記做為唯一識別 ID
                    "time": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
                    "author": author_name.strip() if author_name.strip() else "匿名讀者",
                    "content": comment_content.strip()
                }
                comments.append(new_comment)
                save_comments(comments)
                st.success("留言發表成功！")
                time.sleep(0.5)
                st.rerun()
                
    st.write("---")
    st.write(f"目前共有 {len(comments)} 條留言：")
    
    if not comments:
        st.info("目前尚無留言，歡迎成為第一個留言的人！")
    else:
        # 倒序顯示，最新發表的留言置頂
        for msg in reversed(comments):
            st.markdown(
                f"""
                <div style='background-color: #f8f9fa; padding: 12px; border-radius: 8px; margin-bottom: 10px; border-left: 5px solid #007bff;'>
                    <span style='font-weight: bold; color: #333;'>{msg['author']}</span> 
                    <span style='color: gray; font-size: 11px; margin-left: 10px;'>{msg['time']}</span>
                    <p style='margin-top: 5px; color: #555; font-size: 14px; white-space: pre-wrap;'>{msg['content']}</p>
                </div>
                """, 
                unsafe_allow_html=True
            )
            
    # ==================== 後台管理區 ====================
    st.write("---")
    with st.expander("🛠️ 留言板後台管理功能"):
        # 提供密碼保護，避免一般訪客誤觸
        admin_pwd = st.text_input("請輸入管理員密碼：", type="password", key="admin_pwd_input")
        
        # 預設後台管理密碼：admin888
        if admin_pwd == "admin888":
            st.success("身分驗證成功！已開啟管理權限。")
            if not comments:
                st.info("目前沒有留言可供管理。")
            else:
                st.write("選擇要刪除的留言：")
                for msg in comments:
                    col_msg_info, col_del_btn = st.columns([5, 1])
                    # 預覽顯示格式
                    col_msg_info.write(f"【{msg['author']}】({msg['time']}): {msg['content'][:30]}...")
                    
                    # 點擊對應按鈕即刪除
                    if col_del_btn.button("刪除此留言", key=f"del_{msg['id']}", type="secondary"):
                        # 過濾掉該筆 ID 的留言並寫回檔案
                        comments = [c for c in comments if c["id"] != msg["id"]]
                        save_comments(comments)
                        st.success("留言已順利刪除！")
                        time.sleep(0.5)
                        st.rerun()
        elif admin_pwd:
            st.error("密碼輸入錯誤，請重新確認！")
