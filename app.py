# app.py
import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
import yfinance as yf
import time
import json
import os

import config
import helpers
import storage
import data_fetcher

# ==================== 瀏覽器 Local Storage 輔助管理器 ====================
from streamlit_local_storage import LocalStorage

# 初始化瀏覽器區域儲存物件
localS = LocalStorage()

def get_local_watchlist():
    """優先從瀏覽器讀取自選股，若讀不到則回傳一個乾淨、無隱私疑慮的公用預設值"""
    try:
        val = localS.getItem("my_watchlist_local")
        if val is not None and isinstance(val, list):
            return val
    except Exception:
        pass
    # ❌ 拒絕讀取伺服器上的 my_watchlist.json 共享檔案，保護個人自選股不外洩
    return ["2330", "2303"]  # 預設公用示範股：台積電、聯電

def save_local_watchlist(new_list):
    """將自選股存入訪客自己的瀏覽器（100% 本地隱私，絕不備份至伺服器）"""
    try:
        localS.setItem("my_watchlist_local", new_list)
    except Exception:
        pass
    # ❌ 徹底移除 storage.save_watchlist(new_list) 呼叫，不再往雲端硬碟寫入資料

def get_local_piggy_bank():
    """優先從瀏覽器讀取退休存錢筒持股，若無紀錄則給予一組無關的公用範例（如 0050 持有 1 張）"""
    try:
        val = localS.getItem("my_piggy_bank_local")
        if val is not None and isinstance(val, dict):
            return val
    except Exception:
        pass
    # ❌ 拒絕讀取伺服器上的 my_piggy_bank.json 共享檔案，保護個人持股張數不外洩
    return {"0050": 1.0}  # 預設公用示範持股：0050 持有 1 張

def save_local_piggy_bank(new_dict):
    """將存錢筒存入訪客自己的瀏覽器（100% 本地隱私，絕不備份至伺服器）"""
    try:
        localS.setItem("my_piggy_bank_local", new_dict)
    except Exception:
        pass
    # ❌ 徹底移除 storage.save_piggy_bank(new_dict) 呼叫，不再往雲端硬碟寫入資料

# ==================== 側邊欄公告檔案讀寫輔助函數 ====================
ANNOUNCEMENT_FILE = "announcement.json"

def load_announcement():
    """載入側邊欄公告"""
    if not os.path.exists(ANNOUNCEMENT_FILE):
        return {
            "content": "歡迎造訪台股選股工具！",
            "date": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
        }
    try:
        with open(ANNOUNCEMENT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"content": "歡迎使用選股工具！", "date": ""}

def save_announcement(data):
    """儲存側邊欄公告"""
    try:
        with open(ANNOUNCEMENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"儲存公告失敗: {e}")

# ==================== 💡 新增：一鍵解析全台所有分點 Top 10 買賣超爬蟲 (獨立於 app.py) ====================
def fetch_stock_top_brokers_local(code, days=5):
    """
    爬取指定個股全台「買超」與「賣超」前 10 名的非自選分點券商排行
    """
    from bs4 import BeautifulSoup
    from data_fetcher import unsafe_session  # 沿用專案中的連線 Session 繞過限制
    
    days_map = {1: 1, 3: 3, 5: 5, 7: 5, 10: 10, 20: 20}
    d_param = days_map.get(days, 5)
    
    url = f"https://fubon-ebrokerdj.fbs.com.tw/z/zc/zco/zco.djhtm?a={code}&e=&f=&d={d_param}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    buyers = []
    sellers = []
    
    try:
        res = unsafe_session.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            html = res.content.decode('big5', errors='ignore')
            soup = BeautifulSoup(html, 'html.parser')
            
            rows = soup.find_all('tr')
            for row in rows:
                tds = row.find_all('td')
                # 左右分流表格解析
                if len(tds) >= 10:
                    b_name = tds[0].text.strip()
                    b_net = tds[3].text.strip().replace(',', '')  # 淨買超張數
                    
                    s_name = tds[5].text.strip()
                    s_net = tds[8].text.strip().replace(',', '')  # 淨賣超張數
                    
                    # 過濾雜訊
                    try:
                        b_val = int(b_net)
                        if b_val > 0 and b_name and "券商" not in b_name and "買超" not in b_name:
                            buyers.append({"券商分點": b_name, "淨買超(張)": b_val})
                    except ValueError:
                        pass
                        
                    try:
                        s_val = int(s_net)
                        if s_val > 0 and s_name and "券商" not in s_name and "賣超" not in s_name:
                            sellers.append({"券商分點": s_name, "淨賣超(張)": s_val})
                    except ValueError:
                        pass
    except Exception:
        pass
        
    return buyers[:10], sellers[:10]

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

# 初始化篩選結果記憶體，避免勾選時表格消失
if "tab1_results" not in st.session_state:
    st.session_state.tab1_results = None

# 初始化融資回溯所需的狀態變數，避免 Rerun 時狀態丟失
if "margin_date_used" not in st.session_state:
    st.session_state.margin_date_used = ""
if "margin_is_fallback" not in st.session_state:
    st.session_state.margin_is_fallback = False

# ==================== 100% 執行緒安全防阻擋連線產生器 ====================
def create_yf_session():
    """
    改用 100% 安全、不當機的標準純 Python requests Session。
    配備 Chrome 偽裝標頭，防止 Yahoo 429 阻擋！
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

# ==================== 側邊欄公告檔案讀寫輔助函數 ====================
ANNOUNCEMENT_FILE = "announcement.json"

def load_announcement():
    """載入側邊欄公告"""
    if not os.path.exists(ANNOUNCEMENT_FILE):
        return {
            "content": "歡迎造訪台股選股工具！\n每日精選標的將在此處即時更新，請進入後台設定內容。",
            "date": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
        }
    try:
        with open(ANNOUNCEMENT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"content": "歡迎使用選股工具！", "date": ""}

def save_announcement(data):
    """儲存側邊欄公告"""
    try:
        with open(ANNOUNCEMENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"儲存公告失敗: {e}")

# ==================== 網頁專用精美 HTML 除息行事曆渲染器 ====================
def render_streamlit_calendar(year, month, events):
    """
    利用純 HTML 渲染除息行事曆，支援瀏覽器原生 Tooltip 浮動提示
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
    for key in ['Basic EPS', 'Diluted EPS', 'BasicEarningsPerShare', 'DilutedEarningsPerShare', 'Basic', 'Diluted']:
        if key in stmt.index:
            return stmt.loc[key]
    for idx in stmt.index:
        if "EPS" in str(idx) or "Earnings Per Share" in str(idx):
            return stmt.loc[idx]
    return None

def get_quarter_str(date_obj):
    """
    將財報日期轉換為季度標記字串，例如 2025Q3
    """
    try:
        dt = pd.to_datetime(date_obj)
        q = (dt.month - 1) // 3 + 1
        return f"{dt.year}Q{q}"
    except:
        return ""

# ==================== 側邊欄網站人氣統計與公告看板 ====================
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

# 側邊欄管理者公告看板
st.sidebar.write("---")
st.sidebar.markdown("<h3 style='text-align: center; font-weight: bold;'>📢 管理者公告</h3>", unsafe_allow_html=True)
ann_data = load_announcement()
st.sidebar.markdown(
    f"""
    <div style='background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);'>
        <p style='color: #64748b; font-size: 11px; font-weight: 500; margin-bottom: 6px;'>更新時間：{ann_data.get('date', 'N/A')}</p>
        <p style='color: #1e293b; font-size: 13px; white-space: pre-wrap; line-height: 1.5; margin-bottom: 0;'>{ann_data.get('content', '暫無公告')}</p>
    </div>
    """,
    unsafe_allow_html=True
)

# ==================== 頁首資訊 ====================
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
    
    with st.container(border=True):
        col_cfg1, col_cfg2, col_cfg3 = st.columns([1, 2.5, 2.5])
        
        with col_cfg1:
            days_count = st.selectbox("籌碼區間：", [1, 3, 5, 7, 30, 60, 120], index=1, key="tab1_days")
            
        with col_cfg2:
            chip_options = ["外資", "投信", "自營商", "融資 (資增)", "融資 (餘額最高)", "EPS 暴增", "分點券商"]
            selected_chips = st.multiselect(
                "核心籌碼與信用篩選 (可複選)：",
                options=chip_options,
                default=["外資", "自營商"],
                help="⚠️ 提示：融資餘額數據於每日 21:00~22:00 結算，建議 22:00 後篩選以取得當日最新數據。"
            )
            f_active = "外資" in selected_chips
            t_active = "投信" in selected_chips
            d_active = "自營商" in selected_chips
            m_active = "融資 (資增)" in selected_chips
            m_balance_active = "融資 (餘額最高)" in selected_chips
            eps_surge_active = "EPS 暴增" in selected_chips
            b_active = "分點券商" in selected_chips
            
            brokers_dict = storage.load_custom_brokers()
            if b_active:
                selected_broker_names = st.multiselect(
                    "選定主力分點 (多選取交集，即所有選中的分點都必須買超)：",
                    options=list(brokers_dict.keys()),
                    default=[list(brokers_dict.keys())[0]] if brokers_dict else []
                )
            else:
                selected_broker_names = []

        with col_cfg3:
            tech_options = ["日線多頭排列", "日線 MACD金叉", "月營收雙增", "量能突破 (爆量 2x)"]
            selected_techs = st.multiselect(
                "指標進階過濾 (可複選)：",
                options=tech_options,
                default=["量能突破 (爆量 2x)"]
            )
            filter_ma = "日線多頭排列" in selected_techs
            filter_macd = "日線 MACD金叉" in selected_techs
            filter_rev = "月營收雙增" in selected_techs
            filter_vol = "量能突破 (爆量 2x)" in selected_techs

    st.caption("💡 貼心提醒：當日最新「融資信用交易數據」需等待證交所於每日晚間 **21:00 ~ 22:00** 結算，建議每日 **22:00 後** 進行篩選以獲取當日最即時數據。若勾選多個分點取交集，下載時間可能會增加數秒。")
    if st.button("開始一鍵篩選股票", type="primary", key="btn_run_tab1"):
        with st.spinner("正在進行大數據分析，請稍候..."):
            dfs, t86_dates = data_fetcher.get_recent_data(days_count=days_count)
            if not dfs:
                st.error("無法自證交所取得資料。")
                st.session_state.tab1_results = None
            else:
                raw_data = pd.concat(dfs, ignore_index=True)
                
                tdcc_raw, tdcc_date = data_fetcher.fetch_tdcc_data()
                if tdcc_raw and tdcc_date:
                    tdcc_ratios, tdcc_changes, _ = storage.save_and_get_tdcc_change(tdcc_raw, tdcc_date)
                else:
                    tdcc_ratios, tdcc_changes = {}, {}
                
                # 💡 背景獲取融資數據（自動往前回溯的自癒機制）
                margin_data = {}
                margin_date_used = ""
                st.session_state.margin_is_fallback = False
                
                sorted_dates = sorted(t86_dates, reverse=True) if t86_dates else []
                
                for d_str in sorted_dates:
                    temp_margin = data_fetcher.fetch_all_margin(d_str)
                    if temp_margin:
                        margin_data = temp_margin
                        margin_date_used = d_str
                        if d_str != sorted_dates[0]:
                            st.session_state.margin_is_fallback = True
                        break
                    time.sleep(0.2)
                
                if not margin_date_used and sorted_dates:
                    margin_date_used = sorted_dates[0]
                
                st.session_state.margin_date_used = margin_date_used
                
                revenue_data = data_fetcher.fetch_monthly_revenue()
                
                multi_broker_data = {}
                if b_active and selected_broker_names:
                    days_param = 5 if days_count <= 7 else 20
                    for b_name in selected_broker_names:
                        broker_id = brokers_dict.get(b_name)
                        if broker_id:
                            broker_results = data_fetcher.fetch_broker_net_buys(broker_id, days_param)
                            multi_broker_data[b_name] = {
                                code: item for code, item in broker_results.items() if item["diff"] > 0
                            }

                def check_broker_intersection(code):
                    if not b_active or not selected_broker_names:
                        return True, 0.0
                    
                    total_diff = 0.0
                    for b_name in selected_broker_names:
                        b_data = multi_broker_data.get(b_name, {})
                        if code not in b_data:
                            return False, 0.0
                        total_diff += b_data[code]["diff"]
                    return True, total_diff

                combined = raw_data.copy()
                combined = combined[combined['證券代號'].str.match(r'^[a-zA-Z0-9]{4,6}$')]
                
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
                summary['融資_餘額'] = summary['證券代號'].apply(lambda c: margin_data.get(c, {}).get("today", 0.0))
                
                summary['券商符合交集'] = True
                summary['分點_萬'] = 0.0
                if b_active and selected_broker_names:
                    res_tuples = summary['證券代號'].apply(check_broker_intersection)
                    summary['券商符合交集'] = [t[0] for t in res_tuples]
                    summary['分點_萬'] = [t[1] for t in res_tuples]
                
                filtered_summary = summary.copy()
                filtered_summary['排序得分'] = 0.0
                
                if not selected_chips:
                    st.warning("請至少選取一個核心篩選指標！")
                    st.session_state.tab1_results = None
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
                        filtered_summary['排序得分'] += filtered_summary['融資_餘額']
                    if b_active:
                        filtered_summary = filtered_summary[filtered_summary['券商符合交集'] == True]
                        filtered_summary['排序得分'] += filtered_summary['分點_萬']
                    
                    if eps_surge_active and not (f_active or t_active or d_active or m_active or m_balance_active or b_active):
                        filtered_summary['排序得分'] = (
                            filtered_summary[col_foreign].abs() / 1000 + 
                            filtered_summary[col_trust].abs() / 1000 + 
                            filtered_summary[col_dealer].abs() / 1000 + 
                            filtered_summary['融資_餘額']
                        )
                        top_candidates = filtered_summary.sort_values(by='排序得分', ascending=False).head(80)
                    else:
                        top_candidates = filtered_summary.sort_values(by='排序得分', ascending=False).head(50)
                    
                    final_rows = []
                    yf_session = create_yf_session()
                    
                    for _, row_item in top_candidates.iterrows():
                        code = row_item['證券代號']
                        name = row_item['證券名稱']
                        ticker = f"{code}.TW"
                        
                        rev_item = revenue_data.get(code)
                        if filter_rev:
                            if not rev_item or rev_item.get("yoy", 0) <= 0 or rev_item.get("mom", 0) <= 0:
                                continue
                        
                        is_code_etf = (len(code) >= 5) or (len(code) == 4 and code.startswith("00"))
                        if eps_surge_active and is_code_etf:
                            continue
                        
                        latest_q_eps_val = "ETF無EPS" if is_code_etf else "載入中..."
                        latest_a_eps_val = "ETF無EPS" if is_code_etf else "載入中..."
                        
                        try:
                            time.sleep(0.15)
                            stock = yf.Ticker(ticker, session=yf_session)
                            
                            if ticker in st.session_state.yf_cache:
                                hist = st.session_state.yf_cache[ticker]
                            else:
                                hist = stock.history(period="6mo")
                                if not hist.empty and len(hist) >= 20:
                                    st.session_state.yf_cache[ticker] = hist
                            
                            if hist.empty or len(hist) < 20:
                                continue
                                
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
                                    q_date = q_eps_series.index[0]
                                    q_str = get_quarter_str(q_date)
                                    
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
                                        latest_q_eps_val = f"({q_str}) {round(latest_q_eps, 2)} 元" if q_str else f"{round(latest_q_eps, 2)} 元"
                                        latest_a_eps_val = f"({a_eps_year}年) {round(a_eps_val, 2)} 元"
                                        
                                        latest_a_eps = a_eps_series.iloc[0]
                                        if eps_surge_active and latest_q_eps <= latest_a_eps:
                                            continue
                                    else:
                                        if eps_surge_active:
                                            continue
                                else:
                                    if eps_surge_active:
                                        continue
                                
                            hist['MA5'] = hist['Close'].rolling(5).mean()
                            hist['MA20'] = hist['Close'].rolling(20).mean()
                            latest = hist.iloc[-1]
                            
                            price = latest['Close']
                            ma5 = latest['MA5']
                            ma20 = latest['MA20']
                            
                            latest_vol = latest['Volume']
                            prev_20d_avg_vol = hist['Volume'].iloc[-21:-1].mean()
                            vol_ratio = latest_vol / prev_20d_avg_vol if prev_20d_avg_vol > 0 else 0.0
                            if filter_vol and vol_ratio < 2.0:
                                continue
                                
                            is_bullish = (price > ma5) and (price > ma20) and (ma5 > ma20)
                            ma_status = "均線向上" if is_bullish else "整理/向下"
                            if filter_ma and not is_bullish:
                                continue
                                
                            vol_status_str = f"量增 {vol_ratio:.1f}x" if vol_ratio >= 1.0 else f"量縮 {vol_ratio:.1f}x"
                            ma_status_display = f"{ma_status} ({vol_status_str})"
                            
                            latest_osc_daily, prev_osc_daily = helpers.calculate_macd(hist['Close'])
                            raw_macd_daily = helpers.get_macd_status_str(latest_osc_daily, prev_osc_daily).replace("🟢 ", "").replace("🔴 ", "")
                            
                            if latest_osc_daily is not None and latest_osc_daily <= 0:
                                macd_daily_status = f"🟢 {raw_macd_daily}"
                            else:
                                macd_daily_status = f"🔴 {raw_macd_daily}"
                            
                            if filter_macd and "MACD金叉" not in macd_daily_status and "多頭" not in macd_daily_status:
                                continue
                                
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
                                
                            sr_1m, sr_6m = helpers.get_dynamic_sr(hist, price)
                            prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else price
                            pct_change = ((price - prev_price) / prev_price) * 100
                            
                            # 💡 核心優化：計算選取分點的預估張數與金額
                            broker_details_list = []
                            if b_active and selected_broker_names:
                                for b_name in selected_broker_names:
                                    b_data = multi_broker_data.get(b_name, {})
                                    if code in b_data:
                                        net_buy_wan = b_data[code]["diff"]
                                        est_shares = int(round((net_buy_wan * 10) / price)) if price > 0 else 0
                                        short_b_name = b_name.split(" ")[0]
                                        broker_details_list.append(f"{short_b_name}: {est_shares}張 ({net_buy_wan}萬)")
                            
                            broker_details_str = " | ".join(broker_details_list) if broker_details_list else "無"
                            
                            final_rows.append({
                                "代號": code,
                                "股票名稱": name,
                                "收盤價": round(price, 1),
                                "漲跌幅(%)": round(pct_change, 2),
                                "最新單季EPS": latest_q_eps_val,
                                "去年年度EPS": latest_a_eps_val,
                                "月營收YoY/MoM": helpers.format_rev_growth(rev_item),
                                "外資金額(萬)": round(row_item['外資_張'] * price / 10, 1),
                                "投信金額(萬)": round(row_item['投信_張'] * price / 10, 1),
                                "自營金額(萬)": round(row_item['自營_張'] * price / 10, 1),
                                "分點買超明細": broker_details_str,  # 隱藏此列，改由下方動態指標卡呈現
                                "融資餘額(張)": int(margin_data.get(code, {}).get("today", 0.0)),
                                "融資變動(張)": int(summary.loc[summary['證券代號'] == code, '融資_張'].values[0]),
                                "大戶比例": f"{round(tdcc_ratios.get(code, 0), 2)}%" if code in tdcc_ratios else "N/A",
                                "均線狀態": ma_status_display,
                                "日K_MACD": macd_daily_status,
                                "60m_MACD": macd_60m_status,
                                "短期支壓(1M)": sr_1m,
                                "中期支壓(6M)": sr_6m,
                                "K線圖網址": f"https://tw.stock.yahoo.com/quote/{code}/technical-analysis"
                            })
                        except Exception:
                            continue
                            
                if final_rows:
                    st.session_state.tab1_results = final_rows
                else:
                    st.session_state.tab1_results = []
                    st.warning("無符合當前篩選與過濾條件之個股，請放寬條件再試。")

    # 顯示過濾後的數據結果
    if st.session_state.tab1_results is not None:
        if len(st.session_state.tab1_results) > 0:
            df_res = pd.DataFrame(st.session_state.tab1_results)
            
            if st.session_state.margin_date_used:
                d_str = st.session_state.margin_date_used
                try:
                    formatted_margin_date = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
                except Exception:
                    formatted_margin_date = d_str
                
                if st.session_state.margin_is_fallback:
                    st.info(f"💡 提示：最新一日融資數據尚未發布或讀取失敗，已為您自動回溯採用 **{formatted_margin_date}** 之融資明細。")
                else:
                    st.caption(f"📊 融資數據基準日：{formatted_margin_date}")
            
            st.success(f"篩選完成！共尋獲 {len(df_res)} 檔個股。 (提示：勾選下方表格最左側的股票，可在下方即時查看該股的『主力分點進出卡片與全台排行』！)")
            
            # 💡 隱藏大數據中的「分點買超明細」文字，不佔用儲存格空間
            visible_cols = [c for c in df_res.columns if c != "分點買超明細"]
            
            event = st.dataframe(
                df_res[visible_cols], 
                column_config={
                    "K線圖網址": st.column_config.LinkColumn("看日K線圖", display_text="開啟奇摩股市")
                },
                use_container_width=True,
                on_select="rerun",
                selection_mode="multi-row",
                key="df_res_table_stable"
            )
            
            # 偵測並讀取使用者選取的行數
            selected_rows = event.selection.rows
            if selected_rows:
                # 💡 核心升級一：動態呈現自選分點買超明細儀表板 (Metrics)
                st.write("---")
                st.markdown("### 🎯 已選個股 - 主力分點進出特寫")
                for idx in selected_rows:
                    row_data = df_res.iloc[idx]
                    code = row_data["代號"]
                    name = row_data["股票名稱"]
                    details = row_data.get("分點買超明細", "無")
                    
                    with st.container(border=True):
                        st.markdown(f"**📍 {code} {name}**")
                        
                        st.markdown("**📌 我的自選主力進出：**")
                        if details and details != "無":
                            detail_items = details.split(" | ")
                            cols = st.columns(max(len(detail_items), 4))
                            for i, item in enumerate(detail_items):
                                try:
                                    parts = item.split(": ")
                                    cols[i].metric(label=parts[0], value=parts[1])
                                except:
                                    cols[i].write(item)
                        else:
                            st.caption("自選分點在此股無符合之買超紀錄。")
                        
                        # 💡 核心升級二：不限自選！動態調閱全台灣所有分點 Top 10 排行表
                        st.write("")
                        st.markdown("**🔥 全台所有分點 - 買賣超前 10 名排行 (不設限自選)：**")
                        with st.spinner(f"正在向系統調閱 {code} 的全台主力排行..."):
                            all_buyers, all_sellers = fetch_stock_top_brokers_local(code, days=days_count)
                            
                        if all_buyers or all_sellers:
                            col_b, col_s = st.columns(2)
                            with col_b:
                                st.markdown("🟢 **淨買超排行 Top 10**")
                                df_b = pd.DataFrame(all_buyers)
                                if not df_b.empty:
                                    st.dataframe(df_b, use_container_width=True, hide_index=True)
                                else:
                                    st.caption("無買超排行資料")
                            with col_s:
                                st.markdown("🔴 **淨賣超排行 Top 10**")
                                df_s = pd.DataFrame(all_sellers)
                                if not df_s.empty:
                                    st.dataframe(df_s, use_container_width=True, hide_index=True)
                                else:
                                    st.caption("無賣超排行資料")
                        else:
                            st.error("無法自交易所獲取全台主力排行，可能因連線受限，請稍候重試。")
                
                selected_codes = df_res.iloc[selected_rows]["代號"].tolist()
                st.write("")
                if st.button(f"📥 將這 {len(selected_codes)} 檔股票加入自選股", type="primary", key="btn_add_selected_stable"):
                    current_watchlist = get_local_watchlist()
                    added_count = 0
                    for code in selected_codes:
                        if code not in current_watchlist:
                            current_watchlist.append(code)
                            added_count += 1
                    if added_count > 0:
                        save_local_watchlist(current_watchlist)
                        st.success(f"已成功加入 {added_count} 檔股票至您的專屬自選股！")
                        time.sleep(0.8)
                        st.rerun()
                    else:
                        st.info("您選取的股票早已在自選股清單中囉！")
        else:
            st.warning("查無符合篩選條件之個股。")

# ==================== 【分頁二：我的自選監控】 ====================
with tab2:
    st.subheader("觀察名單即時監控")
    
    watchlist = get_local_watchlist()
    
    with st.container(border=True):
        col_add, col_rem = st.columns(2)
        
        with col_add:
            st.markdown("**➕ 新增自選股**")
            col_add_input, col_add_btn = st.columns([3, 1])
            with col_add_input:
                new_watchlist_code = st.text_input(
                    "輸入股票代號加入自選：", 
                    max_chars=6, 
                    key="add_w", 
                    label_visibility="collapsed",
                    placeholder="請輸入台股代號 (如: 2330)"
                )
            with col_add_btn:
                if st.button("加入自選", use_container_width=True, type="primary", key="btn_add_tab2"):
                    if new_watchlist_code:
                        new_watchlist_code = new_watchlist_code.strip()
                        if new_watchlist_code not in watchlist:
                            watchlist.append(new_watchlist_code)
                            save_local_watchlist(watchlist)
                            st.success(f"已新增 {new_watchlist_code}！")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.info(f"{new_watchlist_code} 已存在名單中。")
                            
        with col_rem:
            st.markdown("**🗑️ 批次移除自選股**")
            if watchlist:
                col_rem_select, col_rem_btn = st.columns([3, 1])
                with col_rem_select:
                    remove_targets = st.multiselect(
                        "選擇要移除的股票：",
                        options=watchlist,
                        default=[],
                        label_visibility="collapsed",
                        placeholder="請選擇待刪除代號"
                    )
                with col_rem_btn:
                    if st.button("確認移除", use_container_width=True, type="secondary", key="btn_rem_tab2"):
                        if remove_targets:
                            updated_watchlist = [code for code in watchlist if code not in remove_targets]
                            save_local_watchlist(updated_watchlist)
                            st.success(f"已成功移除：{', '.join(remove_targets)}！")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.warning("請先選取移除標的！")
            else:
                st.caption("目前監控清單為空。")
                
    st.write("---")
    st.markdown("### 自選股雙週期趨勢與警示看板")
    
    col_refresh, col_codes = st.columns([1, 4])
    with col_refresh:
        if st.button("🔄 重新整理自選數據", use_container_width=True):
            st.session_state.yf_cache.clear()
            st.session_state.yf_60m_cache.clear()
            st.success("快取已清除，正在重新抓取...")
            time.sleep(0.5)
            st.rerun()
    with col_codes:
        if watchlist:
            st.markdown(f"**目前監控中的股票代號：** `{', '.join(watchlist)}`")
        else:
            st.warning("目前監控清單為空。")
            
    if watchlist:
        w_rows = []
        errors_log_tab2 = []
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
                
                is_code_etf_tab2 = (len(code) >= 5) or (len(code) == 4 and code.startswith("00"))
                latest_q_eps_val_tab2 = "ETF無EPS" if is_code_etf_tab2 else "載入中..."
                latest_a_eps_val_tab2 = "ETF無EPS" if is_code_etf_tab2 else "載入中..."
                
                try:
                    time.sleep(0.15)
                    stock = yf.Ticker(ticker, session=yf_session_tab2)
                    hist = stock.history(period="6mo")
                    if hist.empty:
                        ticker = f"{code}.TWO"
                        stock = yf.Ticker(ticker, session=yf_session_tab2)
                        hist = stock.history(period="6mo")
                    
                    if hist.empty or len(hist) < 20:
                        errors_log_tab2.append(f"{code}: 歷史K線數據不足")
                        continue
                        
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
                                q_date = q_eps_series.index[0]
                                q_str = get_quarter_str(q_date)
                                
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
                    
                    latest_osc_daily, prev_osc_daily = helpers.calculate_macd(hist['Close'])
                    raw_macd_daily = helpers.get_macd_status_str(latest_osc_daily, prev_osc_daily).replace("🟢 ", "").replace("🔴 ", "")
                    
                    if latest_osc_daily is not None and latest_osc_daily <= 0:
                        macd_daily_status = f"🟢 {raw_macd_daily}"
                    else:
                        macd_daily_status = f"🔴 {raw_macd_daily}"
                    
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
                    
                    latest_vol = hist['Volume'].iloc[-1]
                    prev_20d_avg_vol = hist['Volume'].iloc[-21:-1].mean()
                    vol_ratio = latest_vol / prev_20d_avg_vol if prev_20d_avg_vol > 0 else 0.0
                    vol_status_str = f"量增 {vol_ratio:.1f}x" if vol_ratio >= 1.0 else f"量縮 {vol_ratio:.1f}x"
                    alert_str_display = f"{alert_str} ({vol_status_str})"
                        
                    sr_1m, sr_6m = helpers.get_dynamic_sr(hist, price)
                    
                    w_rows.append({
                        "代號": code,
                        "股票名稱": name,
                        "現價": round(price, 1),
                        "漲跌幅(%)": round(pct_change, 2),
                        "最新單季EPS": latest_q_eps_val_tab2,
                        "去年年度EPS": latest_a_eps_val_tab2,
                        "月營收YoY/MoM": helpers.format_rev_growth(revenue_data.get(code)),
                        "大戶比例": f"{round(tdcc_ratios.get(code, 0), 2)}%" if code in tdcc_ratios else "N/A",
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

# ==================== 【分頁三：主力券商進出】 ====================
with tab3:
    st.subheader("特寫分點主力特定天數交易明細")
    
    # 自訂分點管理介面 (支援覆寫與直接刪除)
    with st.expander("管理我的自訂券商分點"):
        col_b1, col_b2 = st.columns(2)
        new_b_name = col_b1.text_input("分點名稱 (如: 凱基台北)：")
        new_b_code = col_b2.text_input("分點代號 (4碼，如: 9268)：")
        if st.button("儲存新分點"):
            if new_b_name and new_b_code:
                brokers_dict[new_b_name] = new_b_code.upper() # 強制轉為大寫，避開大小寫資料庫 Bug
                storage.save_custom_brokers(brokers_dict)
                st.success(f"已儲存：{new_b_name} ({new_b_code.upper()})")
                time.sleep(0.5)
                st.rerun()
                
        st.write("---")
        st.markdown("**🗑️ 移除現有自訂分點**")
        col_del_select, col_del_btn = st.columns([3, 1])
        with col_del_select:
            del_b_name = st.selectbox(
                "選擇要刪除的分點名稱：",
                options=["請選擇待刪除分點"] + list(brokers_dict.keys()),
                key="del_broker_select"
            )
        with col_del_btn:
            st.write("") # 微調對齊
            if st.button("確認刪除", type="secondary", use_container_width=True, key="btn_del_broker"):
                if del_b_name != "請選擇待刪除分點":
                    if del_b_name in brokers_dict:
                        del brokers_dict[del_b_name]
                        storage.save_custom_brokers(brokers_dict)
                        st.success(f"已成功移除：{del_b_name}")
                        time.sleep(0.5)
                        st.rerun()
                else:
                    st.warning("請先選取要刪除的分點！")
                
    col_q1, col_q2, col_q3 = st.columns(3)
    target_broker = col_q1.selectbox("選擇統計主力分點：", list(brokers_dict.keys()), key="broker_tab3")
    target_days = col_q2.selectbox("統計天數：", ["近1日", "近5日", "近10日", "近20日"], index=1)
    target_filter = col_q3.selectbox("過濾進出方向：", ["全部進出", "僅顯示買超", "僅顯示賣超"])
    
    if st.button("開始查詢主力買賣超"):
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
                        "進出方向": "淨買超" if diff > 0 else "淨賣超"
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
    now_tw = datetime.now(timezone(timedelta(hours=8)))
    if "cal_year" not in st.session_state:
        st.session_state.cal_year = now_tw.year
    if "cal_month" not in st.session_state:
        st.session_state.cal_month = now_tw.month
    if "etf_events" not in st.session_state:
        st.session_state.etf_events = {}

    st.subheader("熱門與主動式 ETF 動態息收與殖利率看板")
    
    hot_etfs = storage.load_custom_etfs()
    
    col_main_left, col_main_right = st.columns([3, 1.2])
    
    with col_main_left:
        col_e1, col_e2 = st.columns([1, 2])
        with col_e1:
            new_etf_code = st.text_input("新增自選 ETF (代碼)：", max_chars=6, key="add_etf_code")
            if st.button("新增 ETF"):
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
            if st.button("刪除選中 ETF", type="secondary"):
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
            
            yf_session_tab4 = create_yf_session()
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
                        "除息提醒狀態": data["status"].replace("🔔 ", "").replace("🔴 ", "").replace("⏳ ", "")
                    })
                    
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
                
        html_cal = render_streamlit_calendar(
            st.session_state.cal_year, 
            st.session_state.cal_month, 
            st.session_state.etf_events
        )
        st.markdown(html_cal, unsafe_allow_html=True)
        st.caption("提示：滑鼠懸停在紅色的除息日期上，可觀看當天除息 ETF 與金額詳情。")

    st.write("---")
    st.subheader("我的股息退休存錢筒 (複利配息計算機)")
    piggy_bank_data = get_local_piggy_bank()
    
    col_p1, col_p2 = st.columns([1, 3])
    with col_p1:
        p_code = st.text_input("ETF 代號：", max_chars=6, key="pb_c")
        
        col_z_in, col_g_in = st.columns(2)
        with col_z_in:
            p_zhang = st.number_input("持有張數：", min_value=0, step=1, value=0, key="pb_z_val")
        with col_g_in:
            p_gu = st.number_input("零股股數：", min_value=0, max_value=999, step=1, value=0, key="pb_g_val")
            
        if st.button("更新持股"):
            if p_code:
                p_code = p_code.upper().strip()
                total_shares = (p_zhang * 1000 + p_gu) / 1000.0
                if total_shares <= 0:
                    st.warning("請輸入有效的張數或股數！")
                else:
                    piggy_bank_data[p_code] = total_shares
                    save_local_piggy_bank(piggy_bank_data)
                    st.success(f"持股已更新：{p_code} {p_zhang}張 {p_gu}股 (共 {total_shares} 張)")
                    time.sleep(0.5)
                    st.rerun()
                
        p_del = st.text_input("要移除的代號：", max_chars=6, key="pb_del")
        if st.button("移除持股"):
            p_del = p_del.upper().strip()
            if p_del in piggy_bank_data:
                del piggy_bank_data[p_del]
                save_local_piggy_bank(piggy_bank_data)
                st.success(f"已移除持股：{p_del}")
                time.sleep(0.5)
                st.rerun()
                
    with col_p2:
        st.write("退休被動收入配息模擬清單：")
        pb_rows = []
        total_market_value = 0.0
        total_annual_dividend = 0.0
        total_selected_month_dividend = 0.0
        
        for code, shares in piggy_bank_data.items():
            data = data_fetcher.fetch_etf_dividend_details(code, upcoming_dict)
            if data:
                price = data["price"]
                current_year_sum_val = data.get("current_year_sum_val", 0.0)
                latest_div_value = data.get("latest_div_value", 0.0)
                ex_date_str = data.get("ex_date", "N/A")
                
                total_gu = int(round(shares * 1000))
                display_zhang = total_gu // 1000
                display_gu = total_gu % 1000
                
                if display_gu > 0:
                    shares_str = f"{display_zhang} 張 {display_gu} 股"
                else:
                    shares_str = f"{display_zhang} 張"
                
                est_annual = total_gu * current_year_sum_val
                market_val = total_gu * price
                
                total_market_value += market_val
                total_annual_dividend += est_annual
                
                ex_month = None
                ex_year = None
                try:
                    ex_date_obj = datetime.strptime(ex_date_str, "%Y/%m/%d")
                    ex_month = ex_date_obj.month
                    ex_year = ex_date_obj.year
                except:
                    pass
                    
                if ex_month == st.session_state.cal_month and ex_year == st.session_state.cal_year:
                    total_selected_month_dividend += total_gu * latest_div_value
                
                pb_rows.append({
                    "代號": code,
                    "持股規格": shares_str,
                    "總股數": f"{total_gu:,} 股",
                    "現價": f"{round(price, 1)} 元",
                    "預估單股年配息": f"{current_year_sum_val} 元",
                    "預估年領股息": f"{int(est_annual):,} 元",
                    "持股市值": f"{int(market_val):,} 元"
                })
        if pb_rows:
            st.dataframe(pd.DataFrame(pb_rows), use_container_width=True)
            
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
    
    comments = load_comments()
    
    with st.form("comment_form", clear_on_submit=True):
        col_author, col_submit = st.columns([1, 3])
        author_name = col_author.text_input("您的稱呼：", max_chars=10, value="匿名讀者")
        comment_content = st.text_area("留言內容：", max_chars=200, placeholder="歡迎在這裡分享您的想法或回饋...")
        submitted = st.form_submit_button("送出留言")
        
        if submitted:
            if not comment_content.strip():
                st.warning("請填寫留言內容！")
            else:
                new_comment = {
                    "id": int(time.time() * 1000),
                    "time": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
                    "author": author_name.strip() if author_name.strip() else "匿名讀者",
                    "content": comment_content.strip(),
                    "reply": "",
                    "reply_time": ""
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
        for msg in reversed(comments):
            reply_html = ""
            if "reply" in msg and msg["reply"]:
                reply_time_str = f" <span style='color: gray; font-size: 11px; margin-left: 10px;'>({msg.get('reply_time', '')})</span>" if msg.get('reply_time') else ""
                reply_html = f"""
                <div style='background-color: #eef1f6; padding: 10px; border-radius: 6px; margin-top: 10px; border-left: 3px solid #0056b3; margin-left: 15px;'>
                    <span style='font-weight: bold; color: #0056b3;'>版主回覆：</span>{reply_time_str}
                    <p style='margin-top: 5px; color: #444; font-size: 13px; white-space: pre-wrap; margin-bottom: 0;'>{msg['reply']}</p>
                </div>
                """
                
            st.markdown(
                f"""
                <div style='background-color: #f8f9fa; padding: 12px; border-radius: 8px; margin-bottom: 10px; border-left: 5px solid #007bff;'>
                    <span style='font-weight: bold; color: #333;'>{msg['author']}</span> 
                    <span style='color: gray; font-size: 11px; margin-left: 10px;'>{msg['time']}</span>
                    <p style='margin-top: 5px; color: #555; font-size: 14px; white-space: pre-wrap; margin-bottom: 5px;'>{msg['content']}</p>
                    {reply_html}
                </div>
                """, 
                unsafe_allow_html=True
            )
            
    st.write("---")
    with st.expander("🛠️ 留言板後台管理功能"):
        admin_pwd = st.text_input("請輸入管理員密碼：", type="password", key="admin_pwd_input")
        
        if admin_pwd == "admin888":
            st.success("身分驗證成功！已開啟管理權限。")
            
            st.write("### 📢 編輯側邊欄公告")
            current_ann = load_announcement()
            new_ann_text = st.text_area(
                "請輸入公告內容（支援多行輸入，可用來發布每日精選標的等）：",
                value=current_ann.get("content", ""),
                height=150,
                help="儲存後，所有造訪本網頁的人都會立刻在側邊欄看到此公告內容。"
            )
            if st.button("儲存並發布公告", type="primary", key="save_ann_btn_tab5"):
                updated_ann = {
                    "content": new_ann_text.strip(),
                    "date": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
                }
                save_announcement(updated_ann)
                st.success("公告已成功儲存並同步發布至側邊欄！")
                time.sleep(0.5)
                st.rerun()
                
            st.write("---")
            if not comments:
                st.info("目前沒有留言可供管理。")
            else:
                st.write("### 留言管理與回復面板")
                for msg in comments:
                    st.write("---")
                    col_msg_info, col_del_btn = st.columns([5, 1])
                    col_msg_info.markdown(f"**【{msg['author']}】** ({msg['time']}):  \n{msg['content']}")
                    
                    if col_del_btn.button("刪除此留言", key=f"del_{msg['id']}", type="secondary"):
                        comments = [c for c in comments if c["id"] != msg["id"]]
                        save_comments(comments)
                        st.success("留言已順利刪除！")
                        time.sleep(0.5)
                        st.rerun()
                        
                    has_reply = "reply" in msg and msg["reply"]
                    if has_reply:
                        st.info(f"當前已回覆：{msg['reply']} ({msg.get('reply_time', '')})")
                        
                    reply_input = st.text_input(
                        "回覆此留言：" if not has_reply else "修改回覆內容：",
                        value=msg.get("reply", ""),
                        key=f"rep_input_{msg['id']}"
                    )
                    
                    col_rep_btn1, col_rep_btn2 = st.columns([1.5, 4])
                    
                    if col_rep_btn1.button("送出/修改回覆", key=f"rep_btn_{msg['id']}", type="primary"):
                        if reply_input.strip():
                            for c in comments:
                                if c["id"] == msg["id"]:
                                    c["reply"] = reply_input.strip()
                                    c["reply_time"] = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                                    break
                            save_comments(comments)
                            st.success("回覆送出成功！")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.warning("請填寫回覆內容！")
                            
                    if has_reply and col_rep_btn2.button("刪除此回覆", key=f"rep_del_{msg['id']}", type="secondary"):
                        for c in comments:
                            if c["id"] == msg["id"]:
                                c["reply"] = ""
                                c["reply_time"] = ""
                                break
                        save_comments(comments)
                        st.success("已清除回覆！")
                        time.sleep(0.5)
                        st.rerun()
                        
        elif admin_pwd:
            st.error("密碼輸入錯誤，請重新確認！")
