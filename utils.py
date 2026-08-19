# utils.py
import os
import json
import pandas as pd
import streamlit as st
from datetime import datetime, timezone, timedelta
from streamlit_local_storage import LocalStorage

localS = LocalStorage()

def safe_int(val):
    try:
        if val is None or pd.isna(val):
            return 0
        return int(val)
    except:
        return 0

def get_local_watchlist():
    try:
        val = localS.getItem("my_watchlist_local")
        if val is not None and isinstance(val, list):
            return val
    except:
        pass
    return ["2330", "2303"]

def save_local_watchlist(new_list):
    try:
        localS.setItem("my_watchlist_local", new_list)
    except:
        pass

def get_local_piggy_bank():
    try:
        val = localS.getItem("my_piggy_bank_local")
        if val is not None and isinstance(val, dict):
            return val
    except:
        pass
    return {"0050": 1.0}

def save_local_piggy_bank(new_dict):
    try:
        localS.setItem("my_piggy_bank_local", new_dict)
    except:
        pass

ANNOUNCEMENT_FILE = "announcement.json"

def load_announcement():
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
    try:
        with open(ANNOUNCEMENT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"儲存公告失敗: {e}")

def fetch_stock_top_brokers_local(code, days=5):
    from bs4 import BeautifulSoup
    from data_fetcher import unsafe_session
    days_map = {1: 1, 3: 3, 5: 5, 7: 5, 10: 10, 15: 15, 20: 20, 30: 20, 60: 20, 120: 20}
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
                if len(tds) >= 10:
                    b_name = tds[0].text.strip()
                    b_net = tds[3].text.strip().replace(',', '')
                    s_name = tds[5].text.strip()
                    s_net = tds[8].text.strip().replace(',', '')
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
    except:
        pass
    return buyers[:10], sellers[:10]

def create_yf_session():
    import requests as std_requests
    session = std_requests.Session()
    session.verify = False
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7"
    })
    return session

COMMENTS_FILE = "comments.json"

def load_comments():
    if not os.path.exists(COMMENTS_FILE):
        return []
    try:
        with open(COMMENTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_comments(comments):
    try:
        with open(COMMENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(comments, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"儲存留言失敗: {e}")

def render_streamlit_calendar(year, month, events):
    import calendar
    cal = calendar.Calendar(calendar.SUNDAY)
    month_days = cal.monthdayscalendar(year, month)
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
                    tooltip_text = f"除息預告 ({year}/{month:02d}/{day:02d})：&#13;" + "&#13;".join([f"{ev['code']} {ev['name']}: {ev['amount']}" for ev in day_events])
                    row_cells.append(
                        f"<td style='{cell_style} background-color: #ffcccc; color: #cc0000; font-weight: bold; cursor: pointer;' title='{tooltip_text}'>{day}</td>"
                    )
                else:
                    now_tw = datetime.now(timezone(timedelta(hours=8))).date()
                    if target_date == now_tw:
                        row_cells.append(f"<td style='{cell_style} background-color: #007bff; color: white; font-weight: bold;'>{day}</td>")
                    else:
                        row_cells.append(f"<td style='{cell_style}'>{day}</td>")
            rows_html.append(f"<tr>{''.join(row_cells)}</tr>")
    return f"<table style='width: 100%; border-collapse: collapse; font-family: sans-serif;'><thead><tr>{header_html}</tr></thead><tbody>{''.join(rows_html)}</tbody></table>"

def get_eps_from_stmt(stmt):
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
    try:
        dt = pd.to_datetime(date_obj)
        q = (dt.month - 1) // 3 + 1
        return f"{dt.year}Q{q}"
    except:
        return ""