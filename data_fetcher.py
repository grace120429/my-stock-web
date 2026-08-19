# data_fetcher.py
import time
import re
import random  # 💡 引入隨機模組用於輪替瀏覽器標頭
from datetime import datetime, timedelta, timezone
import pandas as pd
import yfinance as yf
from io import StringIO
from bs4 import BeautifulSoup
import requests as std_requests
import streamlit as st
from config import unsafe_session
import helpers

# ==================== 官方雙月歷史日行情直連備用機制 ====================
def fetch_historical_data_official_fallback(code, is_listed=True):
    """
    當 Yahoo Finance 徹底被 429 阻擋封鎖時，此處啟動「官方雙月歷史日行情直連自癒機制」。
    向台灣證交所與櫃買中心官方 JSON API 查詢「本月」與「前一個月」的個股日成交行情，
    並拼接成 K 線 DataFrame！這是不限海外 IP、100% 穩定的官方直連方案。 [1]
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    now_tw = datetime.now(timezone(timedelta(hours=8)))
    # 取得本月與上個月的首日 YYYYMM01 字串
    current_month_str = now_tw.strftime("%Y%m01")
    last_month_date = now_tw - timedelta(days=28)
    last_month_str = last_month_date.strftime("%Y%m01")
    
    closes, opens, highs, lows, volumes, dates = [], [], [], [], [], []
    
    # 進行本月與上月的雙月抓取
    for month_query in [last_month_str, current_month_str]:
        if is_listed:
            # 1. 上市股票直連證交所官方 STOCK_DAY API
            url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={month_query}&stockNo={code}"
            try:
                res = unsafe_session.get(url, headers=headers, timeout=6, verify=False)
                if res.status_code == 200:
                    json_data = res.json()
                    data = json_data.get("data", [])
                    if data:
                        for row in data:
                            if len(row) >= 7:
                                # 民國日期 "115/08/03" -> 轉換為 Datetime
                                date_raw = str(row[0]).strip()
                                parsed_dt = helpers.parse_taiwan_date(date_raw)
                                if parsed_dt:
                                    try:
                                        p_open = float(row[3].replace(',', '').strip())
                                        p_high = float(row[4].replace(',', '').strip())
                                        p_low = float(row[5].replace(',', '').strip())
                                        p_close = float(row[6].replace(',', '').strip())
                                        p_vol = float(row[1].replace(',', '').strip())  # 成交股數
                                        
                                        dates.append(datetime(parsed_dt.year, parsed_dt.month, parsed_dt.day, tzinfo=timezone(timedelta(hours=8))))
                                        opens.append(p_open)
                                        highs.append(p_high)
                                        lows.append(p_low)
                                        closes.append(p_close)
                                        volumes.append(p_vol)
                                    except:
                                        continue
            except:
                pass
        else:
            # 2. 上櫃股票直連櫃買中心官方 daily_trading_info API
            # 民國月份格式 例如 "115/08"
            try:
                yr = int(month_query[:4]) - 1911
                mo = month_query[4:6]
                roc_month = f"{yr}/{mo}"
            except:
                continue
                
            url = f"https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/daily_trading_info_result.php?l=zh-tw&o=json&d={roc_month}&s={code}"
            try:
                res = unsafe_session.get(url, headers=headers, timeout=6, verify=False)
                if res.status_code == 200:
                    json_data = res.json()
                    data = json_data.get("aaData", [])
                    if data:
                        for row in data:
                            if len(row) >= 7:
                                date_raw = str(row[0]).strip()
                                parsed_dt = helpers.parse_taiwan_date(date_raw)
                                if parsed_dt:
                                    try:
                                        p_open = float(row[3].replace(',', '').strip())
                                        p_high = float(row[4].replace(',', '').strip())
                                        p_low = float(row[5].replace(',', '').strip())
                                        p_close = float(row[6].replace(',', '').strip())
                                        p_vol = float(row[1].replace(',', '').strip())  # 成交股數
                                        
                                        dates.append(datetime(parsed_dt.year, parsed_dt.month, parsed_dt.day, tzinfo=timezone(timedelta(hours=8))))
                                        opens.append(p_open)
                                        highs.append(p_high)
                                        lows.append(p_low)
                                        closes.append(p_close)
                                        volumes.append(p_vol)
                                    except:
                                        continue
            except:
                pass
                
    # 組合 DataFrame
    if dates and closes:
        df = pd.DataFrame({
            "Open": opens,
            "High": highs,
            "Low": lows,
            "Close": closes,
            "Volume": volumes,
            "Dividends": [0.0] * len(dates),
            "Stock Splits": [0.0] * len(dates)
        }, index=dates)
        # 去除重複日期索引並由舊到新排序
        df = df[~df.index.duplicated(keep='first')].sort_index()
        return df
    return pd.DataFrame()

# ==================== 原生 API 直連繞過機制 (429 Bypass) ====================
def fetch_historical_data_direct_fallback(ticker, range_str="6mo"):
    """
    當 yfinance 遭到 429 封鎖時，此函式使用原生 requests 直接連線 Yahoo Query1 Chart API。
    搭配偽裝隨機 Chrome/Safari 標頭與直接 JSON 解析，高機率繞過 429 限制！ [1]
    """
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, Gecko) Version/17.2 Safari/605.1.15",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
    ]
    
    # 轉換 period 為 Chart API 採用的 range 參數
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range={range_str}&interval=1d"
    headers = {
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://finance.yahoo.com/"
    }
    
    for s in [std_requests, unsafe_session]:
        try:
            res = s.get(url, headers=headers, timeout=6, verify=False)
            if res.status_code == 200:
                json_data = res.json()
                chart = json_data.get("chart", {})
                result = chart.get("result", [])
                if result:
                    res_data = result[0]
                    timestamp = res_data.get("timestamp", [])
                    indicators = res_data.get("indicators", {})
                    quote = indicators.get("quote", [{}])[0]
                    adjclose = indicators.get("adjclose", [{}])[0].get("adjclose", [])
                    
                    # 擷取 K 線數據
                    opens = quote.get("open", [])
                    highs = quote.get("high", [])
                    lows = quote.get("low", [])
                    closes = quote.get("close", []) if not adjclose else adjclose  # 優先採用調整後收盤價
                    volumes = quote.get("volume", [])
                    
                    # 擷取歷史配息事件 (確保 ETF 功能不受影響) [1]
                    dividends_col = [0.0] * len(timestamp)
                    events = res_data.get("events", {})
                    dividends_data = events.get("dividends", {})
                    if dividends_data:
                        for ts_str, div_info in dividends_data.items():
                            try:
                                ts_val = int(ts_str)
                                if ts_val in timestamp:
                                    idx = timestamp.index(ts_val)
                                    dividends_col[idx] = float(div_info.get("amount", 0.0))
                            except:
                                pass
                    
                    # 轉換為 Pandas DataFrame (欄位與 yfinance 保持完全一致)
                    if timestamp and opens and closes:
                        dates = [datetime.fromtimestamp(ts, tz=timezone(timedelta(hours=8))) for ts in timestamp]
                        df = pd.DataFrame({
                            "Open": opens,
                            "High": highs,
                            "Low": lows,
                            "Close": closes,
                            "Volume": volumes,
                            "Dividends": dividends_col,
                            "Stock Splits": [0.0] * len(timestamp)
                        }, index=dates)
                        
                        df = df.dropna(subset=["Close"])
                        if not df.empty:
                            return df
        except Exception:
            pass
    return pd.DataFrame()

# ==================== 歷史資料全域安全快取 ====================
@st.cache_data(ttl=14400)
def fetch_historical_data_cached(ticker, period="6mo"):
    # 提取代碼與判斷上市櫃
    code = ticker.split('.')[0]
    is_listed = ".TW" in ticker.upper()

    # 1. 優先嘗試標準 yfinance 抓取
    try:
        stock = yf.Ticker(ticker, session=unsafe_session)
        hist = stock.history(period=period)
        if hist is not None and not hist.empty:
            return hist
    except Exception:
        pass
        
    # 2. 若被 429 阻擋，自動啟用「原生 JSON 直接連線自癒機制」繞過封鎖 [1]
    hist_fallback = fetch_historical_data_direct_fallback(ticker, range_str=period)
    if hist_fallback is not None and not hist_fallback.empty:
        return hist_fallback
        
    # 3. 💡 終極自癒防護：若前兩者皆被 Yahoo 阻擋（雲端 IP 被完全封鎖），自動直連台灣官方「證交所/櫃買中心」 [1]
    hist_official = fetch_historical_data_official_fallback(code, is_listed=is_listed)
    if hist_official is not None and not hist_official.empty:
        return hist_official
        
    # 三者皆墨才拋出錯誤，確保 Streamlit 不快取失敗空值 [1]
    raise RuntimeError(f"All 3 K-line sources (Yahoo, Direct, and TWSE Official) failed for {ticker}")

# ==================== 上市法人買賣超資料抓取 (TWSE) ====================
def fetch_twse_t86(date_str):
    """
    抓取上市法人買賣超日報
    """
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={date_str}&selectType=ALLBUT0999"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = unsafe_session.get(url, headers=headers, timeout=10)
        if res.status_code != 200: return None
        json_data = res.json()
        if json_data.get("stat") != "OK": return None
        
        data, fields = None, None
        if "data" in json_data:
            data = json_data["data"]
            fields = json_data["fields"]
        elif "tables" in json_data:
            for table in json_data["tables"]:
                if "data" in table:
                    data = table["data"]
                    fields = table["fields"]
                    break
        if not data or not fields: return None
        df = pd.DataFrame(data, columns=fields)
        df.columns = [col.strip() for col in df.columns]
        return df
    except Exception:
        return None

# ==================== 上櫃法人買賣超資料抓取 (TPEx) ====================
def fetch_tpex_t86(date_str):
    """
    抓取櫃買中心(TPEx)上櫃法人買賣超日報
    """
    try:
        year = int(date_str[:4])
        month = date_str[4:6]
        day = date_str[6:8]
        roc_year = year - 1911
        roc_date = f"{roc_year}/{month}/{day}"
    except Exception:
        return None
        
    url = f"https://www.tpex.org.tw/web/stock/3insti/daily_trade/3itrade_hedge_result.php?l=zh-tw&o=json&se=EW&t=D&d={roc_date}&s=0,asc"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = unsafe_session.get(url, headers=headers, timeout=10)
        if res.status_code != 200: return None
        json_data = res.json()
        
        data = json_data.get("aaData")
        if not data: return None
        
        rows = []
        for r in data:
            if len(r) >= 24:
                code = str(r[0]).strip()
                name = str(r[1]).strip()
                
                if not re.match(r'^[a-zA-Z0-9]{4,6}$', code):
                    continue
                    
                try:
                    foreign_val = float(str(r[4]).replace(',', ''))
                    trust_val = float(str(r[13]).replace(',', ''))
                    dealer_val = float(str(r[22]).replace(',', ''))
                    
                    rows.append({
                        "證券代號": code,
                        "證券名稱": name,
                        "外陸資買賣超股數(不含外資自營商)": foreign_val,
                        "投信買賣超股數": trust_val,
                        "自營商買賣超股數": dealer_val
                    })
                except ValueError:
                    continue
        if not rows: return None
        return pd.DataFrame(rows)
    except Exception:
        return None

# ==================== 全市場信用交易融資餘額抓取 ====================
def fetch_all_margin(date_str):
    margin_dict = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    url_twse = f"https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&date={date_str}&selectType=ALL"
    try:
        res = unsafe_session.get(url_twse, headers=headers, timeout=8, verify=False)
        if res.status_code == 200:
            json_data = res.json()
            if json_data.get("stat") == "OK":
                tables = json_data.get("tables")
                if tables and len(tables) >= 2:
                    data = tables[1].get("data", [])
                    for row in data:
                        if len(row) >= 7:
                            code = str(row[0]).strip()
                            prev_str = str(row[5]).replace(',', '').strip()
                            today_str = str(row[6]).replace(',', '').strip()
                            try:
                                prev_val = float(prev_str)
                                today_val = float(today_str)
                                margin_dict[code] = {
                                    "prev": prev_val,
                                    "today": today_val,
                                    "change": today_val - prev_val
                                }
                            except ValueError:
                                continue
    except Exception:
        pass
        
    url_tpex = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_balance"
    try:
        res = unsafe_session.get(url_tpex, headers=headers, timeout=8, verify=False)
        if res.status_code == 200:
            data = res.json()
            for row in data:
                code = row.get("SecuritiesCompanyCode") or row.get("SecuritiesCode") or row.get("代號")
                if not code:
                    continue
                code = str(code).strip()
                
                prev_str = row.get("MarginPreviousBalance") or row.get("前資餘額") or row.get("MarginBalancePrev")
                today_str = row.get("MarginTodayBalance") or row.get("資餘額") or row.get("MarginBalance")
                
                if prev_str is not None and today_str is not None:
                    try:
                        prev_val = float(str(prev_str).replace(',', ''))
                        today_val = float(str(today_str).replace(',', ''))
                        margin_dict[code] = {
                            "prev": prev_val,
                            "today": today_val,
                            "change": today_val - prev_val
                        }
                    except ValueError:
                        continue
    except Exception:
        pass
        
    return margin_dict

# ==================== 證交所與櫃買中心每月營收 OpenAPI JSON 抓取 (自癒雙模版) ====================
def fetch_monthly_revenue():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    revenue_dict = {}
    
    urls_json = [
        "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",
        "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"
    ]
    
    for url in urls_json:
        for s in [std_requests, unsafe_session]:
            try:
                res = s.get(url, headers=headers, timeout=8, verify=False)
                if res.status_code == 200:
                    data = res.json()
                    if data and isinstance(data, list):
                        first_row = data[0]
                        code_k, yoy_k, mom_k = None, None, None
                        for k in first_row.keys():
                            k_str = str(k).strip()
                            if k_str in ("公司代號", "SecuritiesCompanyCode", "CompanyCode", "SecuritiesCode", "代號", "代碼", "公司代碼"):
                                code_k = k
                            elif any(term in k_str for term in ["去年同月增減", "去年同月比", "YoY", "yoy", "去年同期", "LastYearCompare"]):
                                yoy_k = k
                            elif any(term in k_str for term in ["上月比較增減", "上月增減", "MoM", "mom", "上月比", "PrevMonthCompare"]):
                                mom_k = k
                        
                        if not code_k:
                            code_k = next((k for k in first_row.keys() if "代號" in str(k) or "code" in str(k).lower()), None)
                        if not yoy_k:
                            yoy_k = next((k for k in first_row.keys() if "去年" in str(k) or "yoy" in str(k).lower()), None)
                        if not mom_k:
                            mom_k = next((k for k in first_row.keys() if "上月" in str(k) or "mom" in str(k).lower()), None)
                        
                        if code_k and yoy_k and mom_k:
                            for row in data:
                                code = str(row.get(code_k, "")).strip()
                                if not code or code == "nan":
                                    continue
                                try:
                                    yoy_str = str(row.get(yoy_k, "0")).replace('%', '').replace(',', '').strip()
                                    mom_str = str(row.get(mom_k, "0")).replace('%', '').replace(',', '').strip()
                                    yoy_val = float(yoy_str) if yoy_str and yoy_str not in ('－', '-', 'N/A') else 0.0
                                    mom_val = float(mom_str) if mom_str and mom_str not in ('－', '-', 'N/A') else 0.0
                                    
                                    period_k = next((k for k in row.keys() if "年月" in str(k) or "Period" in str(k)), "N/A")
                                    period_val = str(row.get(period_k, ""))
                                    rev_k = next((k for k in row.keys() if "當月營收" in str(k) or "Revenue" in str(k)), None)
                                    rev_val = float(str(row.get(rev_k, "0")).replace(',', '')) if rev_k else 0.0
                                    
                                    revenue_dict[code] = {
                                        "period": period_val,
                                        "revenue": rev_val,
                                        "yoy": yoy_val,
                                        "mom": mom_val
                                    }
                                except:
                                    continue
                            break
            except Exception:
                pass
                
    if not revenue_dict:
        urls_csv = [
            "https://mopsfin.twse.com.tw/opendata/t187ap05_L.csv",
            "https://mopsfin.twse.com.tw/opendata/t187ap05_O.csv"
        ]
        for url in urls_csv:
            for s in [std_requests, unsafe_session]:
                try:
                    res = s.get(url, headers=headers, timeout=8, verify=False)
                    if res.status_code == 200:
                        csv_text = res.content.decode('utf-8-sig', errors='ignore')
                        df = pd.read_csv(StringIO(csv_text))
                        df.columns = [c.strip() for c in df.columns]
                        
                        col_code = next((c for c in df.columns if "公司代號" in c or "stock" in c.lower()), None)
                        col_yoy = next((c for c in df.columns if "去年同月增減" in c or "yoy" in c.lower()), None)
                        col_mom = next((c for c in df.columns if "上月比較增減" in c or "mom" in c.lower()), None)
                        col_period = next((c for c in df.columns if "資料年月" in c or "period" in c.lower()), None)
                        col_rev = next((c for c in df.columns if "當月營收" in c or "revenue" in c.lower()), None)
                        
                        if col_code and col_yoy and col_mom:
                            for _, row in df.iterrows():
                                code = str(row[col_code]).strip()
                                if not code or code == "nan":
                                    continue
                                try:
                                    yoy_val = float(str(row[col_yoy]).replace(',', '').strip())
                                    mom_val = float(str(row[col_mom]).replace(',', '').strip())
                                    period_val = str(row[col_period]).strip() if col_period else ""
                                    rev_val = float(str(row[col_rev]).replace(',', '')) if col_rev else 0.0
                                    
                                    revenue_dict[code] = {
                                        "period": period_val,
                                        "revenue": rev_val,
                                        "yoy": yoy_val,
                                        "mom": mom_val
                                    }
                                except:
                                    continue
                            break
                except Exception:
                    pass
                    
    return revenue_dict

# ==================== 毫秒級個股/ETF 中文名稱搜尋 ====================
def fetch_stock_name_fast(code):
    url = f"https://tw.stock.yahoo.com/quote/{code}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = unsafe_session.get(url, headers=headers, timeout=5, verify=False)
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")
            title = soup.find("title").text
            if title:
                name = title.split("(")[0].strip()
                if name and "網頁搜尋" not in name and "Yahoo" not in name:
                    return name
    except Exception:
        pass

    url_backup = f"https://query1.finance.yahoo.com/v1/finance/search?q={code}&lang=zh-Hant-TW&quotesCount=1"
    try:
        res = unsafe_session.get(url_backup, headers=headers, timeout=5, verify=False)
        if res.status_code == 200:
            data = res.json()
            quotes = data.get("quotes", [])
            if quotes:
                return quotes[0].get("shortname", "未知")
    except Exception:
        pass
    return "未知"

# ==================== 多週期籌碼資料流調度與雙市場標準化合併處理 ====================
def get_recent_data(days_count=3, progress_callback=None):
    valid_dfs = []
    valid_dates = [] 
    now_tw = datetime.now(timezone(timedelta(hours=8)))
    if now_tw.hour < 16 or (now_tw.hour == 16 and now_tw.minute < 30):
        current_date = now_tw - timedelta(days=1)
    else:
        current_date = now_tw
        
    attempts = 0
    max_attempts = days_count * 2 + 15
    
    while len(valid_dfs) < days_count and attempts < max_attempts:
        if current_date.weekday() >= 5:
            current_date -= timedelta(days=1)
            continue
            
        date_str = current_date.strftime("%Y%m%d")
        
        if progress_callback:
            progress_callback(len(valid_dfs) + 1, days_count, date_str)
            
        df_twse = fetch_twse_t86(date_str)
        time.sleep(0.3)
        df_tpex = fetch_tpex_t86(date_str)
        
        df_combined = None
        if df_twse is not None and df_tpex is not None:
            df_combined = pd.concat([df_twse, df_tpex], ignore_index=True)
        elif df_twse is not None:
            df_combined = df_twse
        elif df_tpex is not None:
            df_combined = df_tpex
            
        delay = 1.0 if days_count >= 30 else 2.0
        time.sleep(delay) 
        
        if df_combined is not None:
            valid_dfs.append(df_combined)
            valid_dates.append(date_str)
            
        current_date -= timedelta(days=1)
        attempts += 1
    return valid_dfs, valid_dates

# ==================== 匯率抓取模組 ====================
def fetch_twd_data():
    twd_str = "💵 台幣匯率: 載入失敗"
    try:
        twd_ticker = yf.Ticker("USDTWD=X", session=unsafe_session)
        twd_hist = twd_ticker.history(period="5d")
        if not twd_hist.empty and len(twd_hist) >= 2:
            latest_twd = twd_hist['Close'].iloc[-1]
            prev_twd = twd_hist['Close'].iloc[-2]
            twd_change = latest_twd - prev_twd
            twd_pct = (twd_change / prev_twd) * 100
            
            if twd_pct < 0:
                twd_str = f"💵 台幣匯率: {latest_twd:.3f} (升值 {abs(twd_pct):.2f}%)"
            else:
                twd_str = f"💵 台幣匯率: {latest_twd:.3f} (貶值 {twd_pct:.2f}%)"
    except Exception:
        pass
    return twd_str

# ==================== 集保大戶比例 CSV 串流解析 ====================
def fetch_tdcc_data():
    url = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        res = unsafe_session.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            csv_text = res.content.decode('utf-8-sig', errors='ignore')
            df = pd.read_csv(StringIO(csv_text))
            df.columns = [c.strip() for c in df.columns]
            
            col_id, col_level, col_ratio, col_date = None, None, None, None
            for col in df.columns:
                c_clean = col.strip()
                if "證券代號" in c_clean: col_id = col
                elif "持股分級" in c_clean: col_level = col
                elif "占集保庫存數比例" in c_clean or "比例" in c_clean: col_ratio = col
                elif "資料日期" in c_clean: col_date = col
                
            if not (col_id and col_level and col_ratio and col_date):
                return None, None
            
            df[col_id] = df[col_id].astype(str).str.strip()
            df[col_level] = pd.to_numeric(df[col_level], errors='coerce')
            df[col_ratio] = pd.to_numeric(df[col_ratio], errors='coerce')
            df[col_date] = df[col_date].astype(str).str.strip()
            
            df_large = df[(df[col_level] >= 12) & (df[col_level] <= 15)]
            
            unique_dates = sorted(df[col_date].unique())
            all_dates_data = {} 
            
            for d in unique_dates:
                df_d = df_large[df_large[col_date] == d]
                ratio_dict = df_d.groupby(col_id)[col_ratio].sum().to_dict()
                all_dates_data[d] = ratio_dict
                
            return all_dates_data, unique_dates[-1] if unique_dates else ""
    except Exception:
        pass
    return None, None

# ==================== 官方未來除息日程表 ====================
def fetch_upcoming_dividends():
    upcoming_dict = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    url_twse = "https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL"
    try:
        res = unsafe_session.get(url_twse, headers=headers, timeout=8, verify=False)
        if res.status_code == 200:
            data = res.json()
            if data and isinstance(data, list):
                code_k, date_k, amount_k = helpers.discover_keys(data[0])
                for row in data:
                    code = str(row.get(code_k, "")).strip() if code_k else ""
                    date_val = row.get(date_k, "") if date_k else ""
                    amount_val = row.get(amount_k, "") if amount_k else ""
                    
                    if not code or not date_val:
                        continue
                    
                    parsed_date = helpers.parse_taiwan_date(date_val)
                    if not parsed_date:
                        continue
                        
                    try:
                        amount = float(amount_val) if amount_val and "尚未公告" not in str(amount_val) else 0.0
                    except ValueError:
                        amount = 0.0
                        
                    upcoming_dict[code] = {
                        "date": parsed_date,
                        "amount": amount
                    }
    except Exception:
        pass

    url_tpex = "https://www.tpex.org.tw/openapi/v1/tpex_exright_prepost"
    try:
        res = unsafe_session.get(url_tpex, headers=headers, timeout=8, verify=False)
        if res.status_code == 200:
            data = res.json()
            if data and isinstance(data, list):
                code_k, date_k, amount_k = helpers.discover_keys(data[0])
                for row in data:
                    code = str(row.get(code_k, "")).strip() if code_k else ""
                    date_val = row.get(date_k, "") if date_k else ""
                    amount_val = row.get(amount_k, "") if amount_k else ""
                    
                    if not code or not date_val:
                        continue
                        
                    parsed_date = helpers.parse_taiwan_date(date_val)
                    if not parsed_date:
                        continue
                        
                    try:
                        amount = float(amount_val) if amount_val and "尚未公告" not in str(amount_val) else 0.0
                    except ValueError:
                        amount = 0.0
                        
                    if code not in upcoming_dict or upcoming_dict[code]["amount"] == 0:
                        upcoming_dict[code] = {
                            "date": parsed_date,
                            "amount": amount
                        }
    except Exception:
        pass
        
    return upcoming_dict

# ==================== 爬取 MoneyDJ ETF 第一階段「預估配息」自癒模組 ====================
def fetch_moneydj_pre_dividend(code):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    for suffix in [".TW", ".TWO"]:
        url = f"https://www.moneydj.com/ETF/X/Basic/Basic0005.xdjhtm?etfid={code}{suffix}"
        try:
            res = unsafe_session.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                soup = BeautifulSoup(res.text, "html.parser")
                table = soup.find("table", id="ctl00_ctl00_MainContent_MainContent_gvTbl")
                if not table:
                    table = soup.find("table", class_="datalist")
                
                if table:
                    rows = table.find_all("tr")
                    if not rows:
                        continue
                        
                    header_tds = rows[0].find_all(["th", "td"])
                    header_texts = [td.text.strip() for td in header_tds]
                    
                    div_col_idx = -1
                    for idx, text in enumerate(header_texts):
                        if any(k in text for k in ["每單位分配金額", "分配金額", "配息金額", "配息(元)", "金額"]):
                            div_col_idx = idx
                            break
                    if div_col_idx == -1:
                        div_col_idx = 5
                        
                    ex_date_idx = -1
                    for idx, text in enumerate(header_texts):
                        if "除息日" in text:
                            ex_date_idx = idx
                            break
                    if ex_date_idx == -1:
                        ex_date_idx = 1
                        
                    for row in rows[1:]:
                        tds = [td.text.strip() for td in row.find_all("td")]
                        if len(tds) > max(ex_date_idx, div_col_idx):
                            ex_date_str = tds[ex_date_idx].replace("/", "-")
                            div_amount_str = tds[div_col_idx].replace("元", "").strip()
                            try:
                                div_amount = float(div_amount_str)
                                if div_amount > 0:
                                    return ex_date_str, div_amount
                            except ValueError:
                                continue
        except Exception:
            continue
    return None, None

# ==================== ETF 配息與當月配息運算 ====================
def fetch_etf_dividend_details(code, upcoming_dict):
    ticker_tw = f"{code}.TW"
    try:
        hist = fetch_historical_data_cached(ticker_tw, period="1y")
    except Exception:
        try:
            ticker_two = f"{code}.TWO"
            hist = fetch_historical_data_cached(ticker_two, period="1y")
        except Exception:
            return None
            
    try:
        price = hist['Close'].iloc[-1]
        prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else price
        pct_change = ((price - prev_price) / prev_price) * 100
        
        divs = hist['Dividends'][hist['Dividends'] > 0]
        
        dj_ex_date_str, dj_amount = fetch_moneydj_pre_dividend(code)
        if dj_ex_date_str and dj_amount and dj_amount > 0:
            try:
                dj_ex_date = datetime.strptime(dj_ex_date_str, "%Y-%m-%d").date()
                upcoming_item = upcoming_dict.get(code)
                if upcoming_item:
                    if upcoming_item["amount"] == 0.0:
                        upcoming_item["amount"] = dj_amount
                else:
                    now_date = datetime.now(timezone(timedelta(hours=8))).date()
                    if dj_ex_date >= now_date:
                        upcoming_dict[code] = {
                            "date": dj_ex_date,
                            "amount": dj_amount
                        }
            except Exception:
                pass

        upcoming_item = upcoming_dict.get(code)
        
        divs_list = []
        if not divs.empty:
            for dt, val in divs.items():
                divs_list.append((dt.date(), val))
                
        if upcoming_item:
            upcoming_date = upcoming_item["date"]
            if divs.empty or upcoming_date > divs.index[-1].date():
                divs_list.append((upcoming_date, upcoming_item["amount"]))
                
        if not divs_list:
            return {
                "price": price,
                "pct_change": pct_change,
                "frequency": "無資料",
                "last_amount": "N/A",
                "ex_date": "N/A",
                "current_year_sum": "0.00 元",
                "yield": "0.00%",
                "status": "⏳ 待除息公告",
                "latest_div_value": 0.0,
                "current_year_sum_val": 0.0
            }
            
        divs_list.sort(key=lambda x: x[0])
        latest_div_date = divs_list[-1][0]
        latest_div_value = divs_list[-1][1]
        
        one_year_ago = latest_div_date - timedelta(days=365)
        past_year_divs = [val for dt, val in divs_list if dt >= one_year_ago]
        div_count = len(past_year_divs)
        
        if div_count >= 10:
            frequency = "月配"
        elif 3 <= div_count <= 6:
            frequency = "季配"
        elif div_count == 2:
            frequency = "半年配"
        elif div_count == 1:
            frequency = "年配"
        else:
            frequency = f"不定期 ({div_count}次/年)"
            
        current_year = datetime.now(timezone(timedelta(hours=8))).year
        current_year_divs = [val for dt, val in divs_list if dt.year == current_year]
        current_year_sum_val = sum(current_year_divs)
        
        est_yield = (current_year_sum_val / price) * 100 if price > 0 else 0.0
        
        now_date = datetime.now(timezone(timedelta(hours=8))).date()
        
        if latest_div_date >= now_date:
            days_left = (latest_div_date - now_date).days
            status_str = f"🔔 即將除息 (剩 {days_left} 天)"
        else:
            days_since = (now_date - latest_div_date).days
            if days_since <= 30:
                status_str = f"🔴 近期已除息 ({days_since}天前)"
            else:
                status_str = f"⏳ 填息中 (前次 {latest_div_date.strftime('%m/%d')})"
                
        return {
            "price": price,
            "pct_change": pct_change,
            "frequency": frequency,
            "last_amount": f"{latest_div_value:.2f} 元" if latest_div_value > 0 else "待第二階段公告",
            "ex_date": latest_div_date.strftime("%Y/%m/%d"),
            "current_year_sum": f"{current_year_sum_val:.2f} 元",
            "yield": f"{est_yield:.2f}%",
            "status": status_str,
            "latest_div_value": latest_div_value,
            "current_year_sum_val": current_year_sum_val
        }
    except Exception as e:
        print(f"Error fetching ETF {code}: {e}")
        return None

# ==================== 主力券商特定統計天數交易資料抓取 ====================
def fetch_stock_top_brokers(code, days=5):
    """
    爬取指定個股全台「買超」與「賣超」前 10 名的分點券商排行
    """
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
                        if b_val > 0 and b_name and "券商" not in b_name:
                            buyers.append({"券商": b_name, "買超張數": b_val})
                    except ValueError:
                        pass
                        
                    try:
                        s_val = int(s_net)
                        if s_val > 0 and s_name and "券商" not in s_name:
                            sellers.append({"券商": s_name, "賣超張數": s_val})
                    except ValueError:
                        pass
    except Exception as e:
        print(f"Error fetching top brokers for {code}: {e}")
        
    return buyers[:10], sellers[:10]

def fetch_broker_net_buys(broker_id, days):
    broker_id = str(broker_id).upper()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
    }
    hosts = [
        "https://fubon-ebrokerdj.fbs.com.tw",
        "https://jdata.yuanta.com.tw",
        "https://newjust.masterlink.com.tw"
    ]
    
    html_content = ""
    success = False
    for host in hosts:
        url = f"{host}/z/zg/zgb/zgb0.djhtm?a={broker_id}&b={broker_id}&c=E&d={days}"
        try:
            res = unsafe_session.get(url, headers=headers, timeout=8, verify=False)
            if res.status_code == 200:
                decoded_text = res.content.decode('big5', errors='ignore')
                if "主力" in decoded_text or "zgb" in decoded_text or "券商" in decoded_text:
                    html_content = decoded_text
                    success = True
                    break
        except Exception:
            continue
            
    broker_dict = {}
    if not success or not html_content:
        return broker_dict
        
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        for tr in soup.find_all('tr'):
            script = tr.find('script')
            if script and script.text:
                match = re.search(r"GenLink2stk\('(?:AS|OT)?(\w+)','([^']+)'\)", script.text)
                if match:
                    code = match.group(1)
                    name = match.group(2)
                    tds = tr.find_all('td')
                    if len(tds) >= 4:
                        try:
                            buy_val = float(tds[1].text.strip().replace(',', ''))
                            sell_val = float(tds[2].text.strip().replace(',', ''))
                            diff_val = float(tds[3].text.strip().replace(',', ''))
                            
                            buy_wan = round(buy_val / 10.0, 1)
                            sell_wan = round(sell_val / 10.0, 1)
                            diff_wan = round(diff_val / 10.0, 1)
                            
                            broker_dict[code] = {
                                "name": name,
                                "buy": buy_wan,
                                "sell": sell_wan,
                                "diff": diff_wan
                            }
                        except ValueError:
                            continue
    except Exception:
        pass
    return broker_dict

# ==================== 全市場上市櫃股票實收資本額 (股本) 抓取 (自癒雙模版) ====================
@st.cache_data(ttl=14400)
def fetch_stock_capitals():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    capital_dict = {}
    
    urls_json = [
        ("https://openapi.twse.com.tw/v1/opendata/t187ap03_L", True),
        ("https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O", False)
    ]
    
    for url, is_listed in urls_json:
        for s in [std_requests, unsafe_session]:
            try:
                res = s.get(url, headers=headers, timeout=8, verify=False)
                if res.status_code == 200:
                    data = res.json()
                    if data and isinstance(data, list):
                        first_row = data[0]
                        code_k = None
                        cap_k = None
                        
                        for k in first_row.keys():
                            k_str = str(k).strip()
                            if is_listed:
                                if k_str == "公司代號": code_k = k
                                elif k_str == "實收資本額": cap_k = k
                            else:
                                if k_str == "SecuritiesCompanyCode": code_k = k
                                elif k_str in ("PaidInCapital", "實收資本額") or "capital" in k_str.lower(): cap_k = k
                        
                        if not code_k:
                            code_k = next((k for k in first_row.keys() if "代號" in str(k) or "code" in str(k).lower() or "Securities" in str(k)), None)
                        if not cap_k:
                            cap_k = next((k for k in first_row.keys() if "資本" in str(k) or "Capital" in str(k) or "capital" in str(k).lower()), None)
                        
                        if code_k and cap_k:
                            for row in data:
                                code = str(row.get(code_k, "")).strip()
                                if not code or code == "nan":
                                    continue
                                try:
                                    cap_str = str(row.get(cap_k, "0")).replace(',', '').strip()
                                    cap_val = float(cap_str)
                                    capital_dict[code] = round(cap_val / 100000000.0, 2)
                                except (ValueError, TypeError):
                                    continue
                            break
            except Exception:
                pass
                
    if not capital_dict:
        urls_csv = [
            ("https://mopsfin.twse.com.tw/opendata/t187ap03_L.csv", True),
            ("https://mopsfin.twse.com.tw/opendata/t187ap03_O.csv", False)
        ]
        for url, is_listed in urls_csv:
            for s in [std_requests, unsafe_session]:
                try:
                    res = s.get(url, headers=headers, timeout=8, verify=False)
                    if res.status_code == 200:
                        csv_text = res.content.decode('utf-8-sig', errors='ignore')
                        df = pd.read_csv(StringIO(csv_text))
                        df.columns = [c.strip() for c in df.columns]
                        
                        code_col = "公司代號"
                        cap_col = "實收資本額"
                        
                        if code_col in df.columns and cap_col in df.columns:
                            for _, row in df.iterrows():
                                code = str(row[code_col]).strip()
                                if not code or code == "nan":
                                    continue
                                try:
                                    cap_val = float(str(row[cap_col]).replace(',', '').strip())
                                    capital_dict[code] = round(cap_val / 100000000.0, 2)
                                except:
                                    continue
                            break
                except Exception:
                    pass
            
    return capital_dict
