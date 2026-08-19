# tab2_watchlist.py
import streamlit as st
import pandas as pd
import yfinance as yf
import time
import data_fetcher
import helpers
import storage

# 💡 安全重定向引進 [1]
import app_utils as utils

def render_tab2(brokers_dict):
    watchlist = utils.get_local_watchlist()
    
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
                            utils.save_local_watchlist(watchlist)
                            st.success(f"已新增 {new_watchlist_code}！")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.info(f"{new_watchlist_code} 已存在名單中。")
                            
        with col_rem:
            st.markdown("**🗑️ 批次勾選移除自選股**")
            if watchlist:
                with st.expander("👉 展開自選股勾選清單 (可多選一鍵刪除)", expanded=False):
                    cols = st.columns(4)
                    to_remove = []
                    
                    for i, code in enumerate(watchlist):
                        name = data_fetcher.fetch_stock_name_fast(code)
                        label = f"{code} {name}" if name != "未知" else f"{code}"
                        
                        with cols[i % 4]:
                            if st.checkbox(label, key=f"del_chk_{code}"):
                                to_remove.append(code)
                    
                    st.write("")
                    if st.button(f"🗑️ 確認移除已勾選的股票 ({len(to_remove)} 檔)", type="secondary", use_container_width=True):
                        if not to_remove:
                            st.warning("請先勾選您想要移除的自選股！")
                        else:
                            updated_watchlist = [c for c in watchlist if c not in to_remove]
                            utils.save_local_watchlist(updated_watchlist)
                            st.success(f"已成功從您的自選清單移除：{', '.join(to_remove)}！")
                            time.sleep(0.5)
                            st.rerun()
            else:
                st.caption("目前監控清單為空。")
                
    st.write("---")
    st.markdown("### 自選股雙週期趨勢與全方位指標看板")
    st.caption("💡 註：自選股的三大法人籌碼金額（外/投/自）與融資增減，預設是以 **近 5 日** 累計變動為統計基準。")
    
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
        yf_session_tab2 = utils.create_yf_session()
        
        with st.spinner("正在分析自選股籌碼、財報與技術指標，請稍候..."):
            chip_dfs, t86_dates = data_fetcher.get_recent_data(days_count=5)
            summary_chip = pd.DataFrame()
            margin_data = {}
            
            if chip_dfs:
                chip_raw = pd.concat(chip_dfs, ignore_index=True)
                col_foreign, col_trust, col_dealer = None, None, None
                for c in chip_raw.columns:
                    if "外陸資買賣超股數(不含外資自營商)" == c: col_foreign = c
                    elif "投信買賣超股數" == c: col_trust = c
                    elif "自營商買賣超股數" == c: col_dealer = c
                if not col_foreign:
                    for c in chip_raw.columns:
                        if "外陸資買賣超股數" in c or "外資買賣超股數" in c:
                            col_foreign = c
                            break
                if not col_trust:
                    for c in chip_raw.columns:
                        if "投信買賣超" in c:
                            col_trust = c
                            break
                if not col_dealer:
                    for c in chip_raw.columns:
                        if "自營商買賣超股數" in c and "自行買賣" not in c and "避險" not in c:
                            col_dealer = c
                            break
                
                def to_num(val):
                    try: return float(str(val).replace(',', ''))
                    except: return 0.0
                
                if col_foreign: chip_raw[col_foreign] = chip_raw[col_foreign].apply(to_num)
                if col_trust: chip_raw[col_trust] = chip_raw[col_trust].apply(to_num)
                if col_dealer: chip_raw[col_dealer] = chip_raw[col_dealer].apply(to_num)
                
                summary_chip = chip_raw.groupby(['證券代號']).agg({
                    col_foreign: 'sum' if col_foreign else 'max',
                    col_trust: 'sum' if col_trust else 'max',
                    col_dealer: 'sum' if col_dealer else 'max'
                }).reset_index()
                
                summary_chip['外資_張'] = summary_chip[col_foreign] / 1000 if col_foreign else 0
                summary_chip['投信_張'] = summary_chip[col_trust] / 1000 if col_trust else 0
                summary_chip['自營_張'] = summary_chip[col_dealer] / 1000 if col_dealer else 0

            if t86_dates:
                sorted_dates = sorted(t86_dates, reverse=True)
                for d_str in sorted_dates:
                    temp_margin = data_fetcher.fetch_all_margin(d_str)
                    if temp_margin:
                        margin_data = temp_margin
                        break
                    time.sleep(0.1)

            revenue_data = data_fetcher.fetch_monthly_revenue()
            capital_data = data_fetcher.fetch_stock_capitals()
            
            tdcc_raw, tdcc_date = data_fetcher.fetch_tdcc_data()
            tdcc_ratios, tdcc_changes = {}, {}
            if tdcc_raw and tdcc_date:
                tdcc_ratios, tdcc_changes, _ = storage.save_and_get_tdcc_change(tdcc_raw, tdcc_date)
                
            for code in watchlist:
                try:
                    time.sleep(0.15)
                    ticker = f"{code}.TW"
                    name = data_fetcher.fetch_stock_name_fast(code)
                    
                    is_code_etf_tab2 = (len(code) >= 5) or (len(code) == 4 and code.startswith("00"))
                    latest_q_eps_val_tab2 = "ETF無EPS" if is_code_etf_tab2 else "載入中..."
                    latest_a_eps_val_tab2 = "ETF無EPS" if is_code_etf_tab2 else "載入中..."
                    
                    try:
                        hist = data_fetcher.fetch_historical_data_cached(ticker, period="6mo")
                    except Exception:
                        ticker = f"{code}.TWO"
                        hist = data_fetcher.fetch_historical_data_cached(ticker, period="6mo")
                        
                    if hist.empty or len(hist) < 20:
                        errors_log_tab2.append(f"{code}: 歷史K線數據不足")
                        continue
                        
                    if not is_code_etf_tab2:
                        try:
                            stock = yf.Ticker(ticker, session=yf_session_tab2)
                            try:
                                q_stmt = stock.quarterly_income_stmt
                                a_stmt = stock.income_stmt
                            except:
                                q_stmt = stock.quarterly_financials
                                a_stmt = stock.financials
                            q_eps_series = utils.get_eps_from_stmt(q_stmt)
                            a_eps_series = utils.get_eps_from_stmt(a_stmt)
                            if q_eps_series is not None and not q_eps_series.empty and a_eps_series is not None and not a_eps_series.empty:
                                latest_q_eps = q_eps_series.iloc[0]
                                q_date = q_eps_series.index[0]
                                q_str = utils.get_quarter_str(q_date)
                                
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
                    
                    is_box, box_amp = helpers.calculate_box_consolidation(hist, days=5, exclude_last_day=True)
                    hist['MA5'] = hist['Close'].rolling(5).mean()
                    hist['MA20'] = hist['Close'].rolling(20).mean()
                    latest = hist.iloc[-1]
                    ma5 = latest['MA5']
                    ma20 = latest['MA20']
                    
                    is_bullish = (price > ma5) and (price > ma20) and (ma5 > ma20)
                    ma_status = "均線向上" if is_bullish else "整理/向下"
                    
                    latest_vol = hist['Volume'].iloc[-1]
                    prev_20d_avg_vol = hist['Volume'].iloc[-21:-1].mean()
                    vol_ratio = latest_vol / prev_20d_avg_vol if prev_20d_avg_vol > 0 else 0.0
                    vol_status_str = f"量增 {vol_ratio:.1f}x" if vol_ratio >= 1.0 else f"量縮 {vol_ratio:.1f}x"
                    ma_status_display = f"{ma_status} ({vol_status_str})"

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
                        
                    sr_1m, sr_6m = helpers.get_dynamic_sr(hist, price)
                    
                    row_chip = summary_chip[summary_chip['證券代號'] == code] if not summary_chip.empty else pd.DataFrame()
                    f_shares = row_chip['外資_張'].values[0] if not row_chip.empty else 0.0
                    t_shares = row_chip['投信_張'].values[0] if not row_chip.empty else 0.0
                    d_shares = row_chip['自營_張'].values[0] if not row_chip.empty else 0.0
                    
                    margin_change = 0
                    margin_today = 0
                    if code in margin_data:
                        margin_change = int(margin_data[code].get("change", 0.0))
                        margin_today = int(margin_data[code].get("today", 0.0))
                        
                    stock_cap = capital_data.get(code, 0.0)
                    
                    w_rows.append({
                        "代號": code,
                        "股票名稱": name,
                        "收盤價": round(price, 1),
                        "股本(億)": stock_cap if stock_cap > 0 else None,
                        "漲跌幅(%)": round(pct_change, 2),
                        "最新單季EPS": latest_q_eps_val_tab2,
                        "去年年度EPS": latest_a_eps_val_tab2,
                        "月營收YoY/MoM": helpers.format_rev_growth(revenue_data.get(code)),
                        "外資金額(萬)": round(f_shares * price / 10, 1),
                        "投信金額(萬)": round(t_shares * price / 10, 1),
                        "自營金額(萬)": round(d_shares * price / 10, 1),
                        "融資餘額(張)": margin_today,
                        "融資變動(張)": margin_change,
                        "大戶比例": f"{round(tdcc_ratios.get(code, 0), 2)}%" if code in tdcc_ratios else "N/A",
                        "均線狀態": ma_status_display,
                        "前期箱型振幅": f"{box_amp}%" if is_box else f"{box_amp}% (未整理)",
                        "日K_MACD": macd_daily_status,
                        "60m_MACD": macd_60m_status,
                        "短期支壓(1M)": sr_1m,
                        "中期支壓(6M)": sr_6m,
                        "K線圖網址": f"https://tw.stock.yahoo.com/quote/{code}/technical-analysis"
                    })
                except Exception as ex_tab2:
                    errors_log_tab2.append(f"{code}: {str(ex_tab2)}")
                    continue                  
        
        if w_rows:
            df_w = pd.DataFrame(w_rows)
            
            event_tab2 = st.dataframe(
                df_w,
                column_config={
                    "K線圖網址": st.column_config.LinkColumn("看日K線圖", display_text="開啟奇摩股市")
                },
                use_container_width=True,
                on_select="rerun",
                selection_mode="multi-row",
                key="df_watchlist_table"
            )
            
            selected_rows_tab2 = event_tab2.selection.rows
            if selected_rows_tab2:
                st.write("---")
                st.markdown("### 🎯 已選自選股 - 主力分點進出特寫")
                days_param_tab2 = 5 
                
                for idx in selected_rows_tab2:
                    if idx >= len(df_w):  # 💡 安全越界防禦 [1]
                        continue
                    row_data = df_w.iloc[idx]
                    code = row_data["代號"]
                    name = row_data["股票名稱"]
                    price_val = float(row_data["收盤價"])
                    
                    with st.container(border=True):
                        st.markdown(f"**📍 {code} {name}**")
                        st.markdown("**📌 我的自選主力進出 (近 5 日)：**")
                        broker_details_list = []
                        if brokers_dict:
                            for b_name, b_id in brokers_dict.items():
                                b_data = data_fetcher.fetch_broker_net_buys(b_id, days_param_tab2)
                                if code in b_data:
                                    net_buy_wan = b_data[code]["diff"]
                                    if net_buy_wan > 0:
                                        est_shares = int(round((net_buy_wan * 10) / price_val)) if price_val > 0 else 0
                                        short_b_name = b_name.split(" ")[0]
                                        broker_details_list.append(f"{short_b_name}: {est_shares}張 ({net_buy_wan}萬)")
                                        
                        if broker_details_list:
                            cols = st.columns(max(len(broker_details_list), 4))
                            for i, item in enumerate(broker_details_list):
                                try:
                                    parts = item.split(": ")
                                    cols[i].metric(label=parts[0], value=parts[1])
                                except:
                                    cols[i].write(item)
                        else:
                            st.caption("自選分點在此股近 5 日內無符合之買超紀錄。")
                            
                        st.write("")
                        st.markdown("**🔥 全台所有分點 - 買賣超前 10 名排行 (不設限自選)：**")
                        with st.spinner(f"正在向系統調閱 {code} 的全台主力排行..."):
                            all_buyers, all_sellers = utils.fetch_stock_top_brokers_local(code, days=days_param_tab2)
                            
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
        else:
            st.warning("自選股數據分析失敗，請查看下方診斷報告。")
            
        if errors_log_tab2:
            with st.expander("⚠️ 查看自選背景診斷報告"):
                st.write(errors_log_tab2)
