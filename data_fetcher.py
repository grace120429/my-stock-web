# data_fetcher.py
import time
import re
from datetime import datetime, timedelta, timezone
import pandas as pd
import yfinance as yf
from io import StringIO
from bs4 import BeautifulSoup
import requests as std_requests
from config import unsafe_session
import helpers

# ==================== 三大法人買賣超資料抓取 ====================
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

# ==================== 全市場信用交易融資餘額抓取 ====================
def fetch_all_margin(date_str):
    """
    綜合抓取 上市 (證交所) 與 上櫃 (櫃買中心) 的全市場信用交易融資餘額變動
    """
    margin_dict = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # 1. 抓取上市 (TWSE) 融資數據
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
        
    # 2. 抓取上櫃 (TPEx) 融資數據
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

# ==================== 公開資訊觀測站每月營收 CSV 抓取 ====================
def fetch_monthly_revenue():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    revenue_dict = {}
    
    urls = [
        "https://mopsfin.twse.com.tw/opendata/t187ap05_L.csv",
        "https://mopsfin.twse.com.tw/opendata/t187ap05_O.csv"
    ]
    
    for url in urls:
        try:
            res = unsafe_session.get(url, headers=headers, timeout=8, verify=False)
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
                            rev_val = float(str(row[col_rev]).replace(',', '').strip()) if col_rev else 0.0
                            
                            revenue_dict[code] = {
                                "period": period_val,
                                "revenue": rev_val,
                                "yoy": yoy_val,
                                "mom": mom_val
                            }
                        except (ValueError, TypeError):
                            continue
        except Exception:
            pass
            
    return revenue_dict

# ==================== 毫秒級個股/ETF 中文名稱搜尋 ====================
def fetch_stock_name_fast(code):
    """
    精確爬取 Yahoo 股市台灣網頁標題，確保 100% 取得繁體中文名稱，避免雲端主機因海外 IP 讀取到英文
    """
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
                # 範例："鴻準 (2354) - 股價" -> 取得括號前的 "鴻準"
                name = title.split("(")[0].strip()
                if name and "網頁搜尋" not in name and "Yahoo" not in name:
                    return name
    except Exception:
        pass

    # 備份原有 query1 Search API 機制
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

# ==================== 多週期籌碼資料流調度處理 ====================
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
            
        df = fetch_twse_t86(date_str)
        
        delay = 1.0 if days_count >= 30 else 2.0
        time.sleep(delay) 
        
        if df is not None:
            valid_dfs.append(df)
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

# ==================== 集保大戶比例 CSV 串流解析 (安全升級版) ====================
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
        stock = yf.Ticker(ticker_tw, session=unsafe_session)
        hist = stock.history(period="1y")
        if hist.empty:
            ticker_two = f"{code}.TWO"
            stock = yf.Ticker(ticker_two, session=unsafe_session)
            hist = stock.history(period="1y")
            if hist.empty:
                return None
        
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
            
            # 尋找網頁中包含「買超券商」與「賣超券商」的表格
            rows = soup.find_all('tr')
            for row in rows:
                tds = row.find_all('td')
                # ZCO 表格左右分流：左邊是買超，右邊是賣超
                if len(tds) >= 10:
                    b_name = tds[0].text.strip()
                    b_net = tds[3].text.strip().replace(',', '') # 淨買超張數
                    
                    s_name = tds[5].text.strip()
                    s_net = tds[8].text.strip().replace(',', '') # 淨賣超張數
                    
                    # 過濾表頭雜訊，只取數字
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
        
    # 只取前 10 名
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
