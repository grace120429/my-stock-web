# app.py
import streamlit as st
import storage
import data_fetcher
import utils

import tab1_big_data
import tab2_watchlist
import tab3_brokers
import tab4_etfs
import tab5_comments

# 1. 網頁基本設定
st.set_page_config(layout="wide", page_title="台股三大法人飆股選股工具")

# 2. 隱藏 Streamlit 的主選單與 Made with Streamlit 頁尾
hide_streamlit_style = """
            <style>
            header {visibility: hidden;}
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# 3. 初始化全域 yfinance 快取與回溯基準
if "yf_cache" not in st.session_state:
    st.session_state.yf_cache = {}
if "yf_60m_cache" not in st.session_state:
    st.session_state.yf_60m_cache = {}
if "tab1_results" not in st.session_state:
    st.session_state.tab1_results = None
if "margin_date_used" not in st.session_state:
    st.session_state.margin_date_used = ""
if "margin_is_fallback" not in st.session_state:
    st.session_state.margin_is_fallback = False

# 4. 側邊欄：統計人氣與管理者公告
st.sidebar.markdown("<h3 style='text-align: center; font-weight: bold;'>網站數據統計</h3>", unsafe_allow_html=True)
visitor_badge_url = "https://hitscounter.dev/api/hit?url=https%3A%2F%2Fgithub.com%2Fgrace120429%2Fmy-stock-web&label=Total%20Views&color=%23007bff"
st.sidebar.markdown(f"<div style='text-align: center; margin-bottom: 20px;'><img src='{visitor_badge_url}' alt='Views'/></div>", unsafe_allow_html=True)
st.sidebar.markdown("<div style='text-align: center; color: gray; font-size: 11px;'>提示：本計數器由雲端數據庫提供永久累計，每一次頁面載入皆會即時更新。</div>", unsafe_allow_html=True)

st.sidebar.write("---")
st.sidebar.markdown("<h3 style='text-align: center; font-weight: bold;'>📢 管理者公告</h3>", unsafe_allow_html=True)
ann_data = utils.load_announcement()
st.sidebar.markdown(
    f"""
    <div style='background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px; padding: 12px; margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);'>
        <p style='color: #64748b; font-size: 11px; font-weight: 500; margin-bottom: 6px;'>更新時間：{ann_data.get('date', 'N/A')}</p>
        <p style='color: #1e293b; font-size: 13px; white-space: pre-wrap; line-height: 1.5; margin-bottom: 0;'>{ann_data.get('content', '暫無公告')}</p>
    </div>
    """,
    unsafe_allow_html=True
)

# 5. 頁面標題與即時匯率
st.title("台股三大法人飆股選股工具 by Kelly")
twd_str = data_fetcher.fetch_twd_data()
st.info(f"{twd_str}")

# 6. 載入券商清單與建立分頁
brokers_dict = storage.load_custom_brokers()

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "三大法人選股大數據", 
    "我的自選監控", 
    "主力券商進出", 
    "台灣熱門 ETF 配息專區",
    "讀者交流留言區"
])

# 7. 分發執行分頁渲染 [1]
with tab1:
    tab1_big_data.render_tab1(brokers_dict)
with tab2:
    tab2_watchlist.render_tab2(brokers_dict)
with tab3:
    tab3_brokers.render_tab3(brokers_dict)
with tab4:
    tab4_etfs.render_tab4()
with tab5:
    tab5_comments.render_tab5()
