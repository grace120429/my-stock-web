# helpers.py
import tkinter as tk
from datetime import datetime
import pandas as pd
import ttkbootstrap as tb

# ==================== 智慧型滑鼠懸停 Tooltip 組件 ====================
class CanvasTooltip:
    def __init__(self, widget):
        self.widget = widget
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0

    def showtip(self, text, event=None):
        if self.tipwindow or not text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        if event:
            x = event.x_root + 15
            y = event.y_root + 10
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(1)
        tw.wm_geometry(f"+{x}+{y}")
        
        label = tb.Label(
            tw, text=text, justify=tk.LEFT,
            background="#333333", foreground="white",
            relief=tk.SOLID, borderwidth=1,
            font=("Microsoft JhengHei", 9, "bold"),
            padding=(10, 6)
        )
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

# ==================== 智慧欄位與日期解析工具 ====================
def discover_keys(row):
    code_key, date_key, amount_key = None, None, None
    for k in row.keys():
        k_str = str(k).strip()
        if k_str in ("Date", "除權息日期", "除權息交易日", "date", "除息日期", "除權息日期"):
            date_key = k
        elif k_str in ("Code", "代號", "股票代號", "symbol", "code", "SecuritiesCompanyCode", "股票代碼"):
            code_key = k
        elif k_str in ("CashDividend", "現金股利", "股利", "cashDividend", "amount", "現金股利元每股", "現金股利(元/股)"):
            amount_key = k
            
    if not date_key:
        date_key = next((k for k in row.keys() if "日期" in str(k) or "date" in str(k).lower()), None)
    if not code_key:
        code_key = next((k for k in row.keys() if "代號" in str(k) or "code" in str(k).lower() or "symbol" in str(k).lower()), None)
    if not amount_key:
        amount_key = next((k for k in row.keys() if "股利" in str(k) or "dividend" in str(k).lower()), None)
        
    return code_key, date_key, amount_key

def parse_taiwan_date(date_str):
    clean = str(date_str).replace('/', '').replace('-', '').strip()
    if len(clean) == 7:
        try:
            year = int(clean[:3]) + 1911
            month = int(clean[3:5])
            day = int(clean[5:])
            return datetime(year, month, day).date()
        except ValueError:
            pass
    elif len(clean) == 8:
        try:
            year = int(clean[:4])
            month = int(clean[4:6])
            day = int(clean[6:])
            return datetime(year, month, day).date()
        except ValueError:
            pass
    if '/' in date_str:
        parts = date_str.split('/')
        if len(parts) == 3:
            try:
                year = int(parts[0]) + 1911 if int(parts[0]) < 1000 else int(parts[0])
                month = int(parts[1])
                day = int(parts[2])
                return datetime(year, month, day).date()
            except ValueError:
                pass
    return None

# ==================== 多週期成交量剖面 (Volume Profile) 計算 ====================
def calculate_profile_sr(hist_slice, price):
    if hist_slice.empty or len(hist_slice) < 5:
        return "N/A", "N/A"
    
    closes = hist_slice['Close']
    volumes = hist_slice['Volume']
    low_limit = closes.min()
    high_limit = closes.max()
    
    if high_limit != low_limit:
        bins_count = 10 if len(hist_slice) <= 30 else 15
        bin_width = (high_limit - low_limit) / bins_count
        bin_volumes = [0.0] * bins_count
        bin_prices = [low_limit + (i + 0.5) * bin_width for i in range(bins_count)]
        
        for p, v in zip(closes, volumes):
            if pd.isna(p) or pd.isna(v): continue
            bin_idx = int((p - low_limit) / bin_width)
            if bin_idx >= bins_count: bin_idx = bins_count - 1
            if bin_idx < 0: bin_idx = 0
            bin_volumes[bin_idx] += v
            
        profile = sorted(list(zip(bin_prices, bin_volumes)), key=lambda x: x[1], reverse=True)
        
        support_price = None
        for b_price, b_vol in profile:
            if b_price < price:
                support_price = b_price
                break
        resistance_price = None
        for b_price, b_vol in profile:
            if b_price > price:
                resistance_price = b_price
                break
                
        support_val = support_price if support_price is not None else low_limit
        resistance_val = resistance_price if resistance_price is not None else high_limit
        
        return str(round(support_val, 1)), str(round(resistance_val, 1))
    return "N/A", "N/A"

def get_dynamic_sr(hist, price):
    try:
        s_6m, r_6m = calculate_profile_sr(hist, price)
        hist_1m = hist.iloc[-20:] if len(hist) >= 20 else hist
        s_1m, r_1m = calculate_profile_sr(hist_1m, price)
        
        str_1m = f"{s_1m} / {r_1m}"
        str_6m = f"{s_6m} / {r_6m}"
        return str_1m, str_6m
    except Exception:
        return "N/A / N/A", "N/A / N/A"

# ==================== MACD 趨勢指標運算 ====================
def calculate_macd(close_series):
    if len(close_series) < 35:
        return None, None
    fast_ema = close_series.ewm(span=12, adjust=False).mean()
    slow_ema = close_series.ewm(span=26, adjust=False).mean()
    macd_line = fast_ema - slow_ema
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    macd_hist = macd_line - signal_line
    
    latest_osc = macd_hist.iloc[-1]
    prev_osc = macd_hist.iloc[-2] if len(macd_hist) > 1 else latest_osc
    return latest_osc, prev_osc

def get_macd_status_str(latest_osc, prev_osc):
    if latest_osc is None or prev_osc is None:
        return "⚠️ 計算失敗"
    if latest_osc > 0:
        if prev_osc <= 0:
            return "🟢 MACD金叉起漲"
        else:
            return "🟢 MACD多頭(OSC>0)"
    else:
        if prev_osc > 0:
            return "🔴 MACD死叉走弱"
        else:
            return "🔴 MACD空頭(OSC<0)"

# ==================== 營收格式化工具 ====================
def format_rev_growth(rev_item):
    if not rev_item:
        return "N/A"
    try:
        yoy = float(rev_item.get("yoy", 0.0))
        mom = float(rev_item.get("mom", 0.0))
        
        yoy_str = f"+{yoy:.1f}%" if yoy > 0 else f"{yoy:.1f}%"
        mom_str = f"+{mom:.1f}%" if mom > 0 else f"{mom:.1f}%"
        
        return f"{yoy_str} / {mom_str}"
    except (ValueError, TypeError):
        return "N/A"

# ==================== 手動滑鼠拖曳調整欄位順序處理器 (修正版) ====================
class ColumnDragHandler:
    def __init__(self, tree):
        self.tree = tree
        self.drag_col_id = None
        
        # 綁定滑鼠左鍵壓下與放開事件
        self.tree.bind("<ButtonPress-1>", self.on_press, add="+")
        self.tree.bind("<ButtonRelease-1>", self.on_release, add="+")
        
    def on_press(self, event):
        # 壓下時必須點擊在 "heading"（表頭）區域
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            col_num_str = self.tree.identify_column(event.x)  # e.g., "#1", "#2"
            if col_num_str:
                self.drag_col_id = self.tree.column(col_num_str, "id")
        else:
            self.drag_col_id = None
            
    def on_release(self, event):
        if not self.drag_col_id:
            return
            
        # 修正點：放開滑鼠時「不再限制」必須在 heading 區域。
        # 即使使用者的滑鼠在拖曳過程中向下漂移到 cell（資料列）區域，依然能精確定位其水平欄位！
        col_num_str = self.tree.identify_column(event.x)
        if col_num_str:
            target_col_id = self.tree.column(col_num_str, "id")
            if target_col_id and target_col_id != self.drag_col_id:
                # 解決 Tcl 物件/字串解析問題：使用原生 splitlist 解析 displaycolumns 
                dcols_raw = self.tree.cget("displaycolumns")
                dcols = list(self.tree.tk.splitlist(dcols_raw))
                
                if not dcols or dcols == ["#all"]:
                    dcols = list(self.tree["columns"])
                    
                if self.drag_col_id in dcols and target_col_id in dcols:
                    idx_from = dcols.index(self.drag_col_id)
                    dcols.pop(idx_from)
                    idx_to = dcols.index(target_col_id)
                    dcols.insert(idx_to, self.drag_col_id)
                    
                    # 動態重整顯示順序
                    self.tree.configure(displaycolumns=dcols)
                    
        self.drag_col_id = None