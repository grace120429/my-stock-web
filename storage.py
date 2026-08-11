# storage.py
import os
import json

# ==================== 集保大戶變動歷史儲存與計算 ====================
def save_and_get_tdcc_change(all_dates_data, latest_date):
    """
    更新集保大戶比例歷史，並計算最新一週相較於上一週的持股增減變動
    """
    file_path = "tdcc_history.json"
    history = {}
    
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            pass
            
    if all_dates_data:
        for d, data_dict in all_dates_data.items():
            history[d] = data_dict
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
            
    dates = sorted(history.keys())
    prev_date = None
    if len(dates) >= 2:
        if dates[-1] == latest_date:
            prev_date = dates[-2]
            
    changes = {}
    current_data = history.get(latest_date, {})
    prev_data = history.get(prev_date, {}) if prev_date else {}
    
    for code, ratio in current_data.items():
        if code in prev_data:
            changes[code] = ratio - prev_data[code]
        else:
            changes[code] = None
            
    return current_data, changes, latest_date

# ==================== 自訂主力券商資料管理 ====================
def load_custom_brokers():
    """
    載入或初始化自訂券商與分點設定
    """
    file_path = "my_brokers.json"
    default_brokers = {
        "摩根大通 (外資大行)": "8440",
        "台灣摩根士丹利 (外資大行)": "1470",
        "美商高盛 (外資大行)": "1480",
        "美商美林 (外資大行)": "1440",
        "新加坡商瑞銀 (外資大行)": "1650",
        "花旗環球 (外資大行)": "1590",
        "元大證券 (本土最大)": "9800",
        "凱基台北 (本土大戶)": "9268",
        "富邦證券 (本土大戶)": "9676",
        "國泰證券 (本土大戶)": "8880",
        "國泰敦南 (數位大戶)": "8888"
    }
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {k: str(v).lower() for k, v in data.items()}
        except Exception:
            pass
    save_custom_brokers(default_brokers)
    return default_brokers

def save_custom_brokers(brokers_dict):
    """
    儲存自訂主力券商與分點設定至本地
    """
    file_path = "my_brokers.json"
    try:
        formatted_dict = {k: str(v).lower() for k, v in brokers_dict.items()}
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(formatted_dict, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ==================== 自訂 ETF 專區資料管理 ====================
def load_custom_etfs():
    """
    載入或初始化熱門與主動式 ETF 清單
    """
    file_path = "my_etfs.json"
    default_etfs = [
        ("0056", "元大高股息 (高股息)"),
        ("00878", "國泰永續高股息 (高股息)"),
        ("00919", "群益台灣精選高息 (高股息)"),
        ("00929", "復華台灣科技優息 (高股息)"),
        ("0050", "元大台灣50 (市值型)"),
        ("006208", "富邦台50 (市值型)"),
        ("00713", "元大台灣高息低波 (低波高息)"),
        ("00915", "凱基優選高股息30 (高股息)"),
        ("00918", "大華優利高填息30 (填息高息)"),
        # 2026 熱門主動式 ETF
        ("00400A", "國泰動能高息 (主動高息)"),
        ("00401A", "摩根台灣鑫收 (主動高息)"),
        ("00406A", "中信台灣成長 (主動成長)"),
        ("00982A", "群益台灣強棒 (主動強棒)"),
        ("00980A", "野村臺灣優選 (主動優選)"),
    ]
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data:
                    return data
        except Exception:
            pass
    save_custom_etfs(default_etfs)
    return default_etfs

def save_custom_etfs(etf_list):
    """
    儲存自選 ETF 清單至本地
    """
    file_path = "my_etfs.json"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(etf_list, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ==================== 退休配息存錢筒持股管理 ====================
def load_piggy_bank():
    """
    載入本機股息退休存錢筒持股資料
    """
    file_path = "my_piggy_bank.json"
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_piggy_bank(pb_data):
    """
    儲存本機股息退休存錢筒持股資料
    """
    file_path = "my_piggy_bank.json"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(pb_data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# ==================== 我的自選監控清單管理 ====================
def load_watchlist():
    """
    載入自選監控股票代碼清單
    """
    file_path = "my_watchlist.json"
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def save_watchlist(watchlist):
    """
    儲存自選監控股票代碼清單
    """
    file_path = "my_watchlist.json"
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(watchlist, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
