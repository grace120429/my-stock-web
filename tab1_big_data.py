# tab1_big_data.py
import streamlit as st
import pandas as pd
import yfinance as yf
import time
import data_fetcher
import helpers
import storage

# 💡 安全重定向引進 [1]
import app_utils as utils

def render_tab1(brokers_dict):
    st.subheader("核心篩選與指標過濾")
    
    with st.container(border=True):
        col_cfg1, col_cfg2, col_cfg3 = st.columns([1, 2.5, 2.5])
        
        with col_cfg1:
            days_count = st.selectbox("籌碼區間天數：", [1, 3, 5, 7, 15, 30, 60, 120], index=0, key="tab1_days")
            cap_filter_opt = st.selectbox(
                "股本大小篩選：",
                options=["不限股本", "中小型股 (股本 < 50億)", "小型股 (股本 < 20億)", "微型股 (股本 < 10億)", "中大型股 (股本 >= 50億)"],
                index=0,
                key="tab1_cap_filter"
            )
            
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
            
            if b_active:
                selected_broker_names = st.multiselect(
                    "選定主力分點 (多選取交集，即所有選中的分點都必須買超)：",
                    options=list(brokers_dict.keys()),
                    default=[list(brokers_dict.keys())[0]] if brokers_dict else []
                )
            else:
                selected_broker_names = []

        with col_cfg3:
            tech_options = ["日線多頭排列", "日線 MACD金叉", "月營收雙增", "量能突破 (爆量 2x)", "前期箱型整理 (近5日)", "強勢飆股 (近5日漲幅 > 10%)"]
            selected_techs = st.multiselect(
                "指標進階過濾 (可複選)：",
                options=tech_options,
                default=["強勢飆股 (近5日漲幅 > 10%)"]
            )
            filter_ma = "日線多頭排列" in selected_techs
            filter_macd = "日線 MACD金叉" in selected_techs
            filter_rev = "月營收雙增" in selected_techs
            filter_vol = "量能突破 (爆量 2x)" in selected_techs
            filter_box = "前期箱型整理 (近5日)" in selected_techs
            filter_momentum = "強勢飆股 (近5日漲幅 > 10%)" in selected_techs

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
                
                capital_data = data_fetcher.fetch_stock_capitals()
                
                multi_broker_data = {}
                if b_active and selected_broker_names:
                    days_param = 5 if days_count <= 7 else (15 if days_count == 15 else 20)
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
                    yf_session = utils.create_yf_session()
                    yf_fail_count = 0  # 💡 追蹤連線失效次數
                    
                    for _, row_item in top_candidates.iterrows():
                        code = row_item['證券代號']
                        name = row_item['證券名稱']
                        ticker = f"{code}.TW"
                        
                        # 💡 股本大小過濾
                        stock_cap = capital_data.get(code, 0.0)
                        if cap_filter_opt == "中小型股 (股本 < 50億)" and stock_cap >= 50.0:
                            continue
                        elif cap_filter_opt == "小型股 (股本 < 20億)" and stock_cap >= 20.0:
                            continue
                        elif cap_filter_opt == "微型股 (股本 < 10億)" and stock_cap >= 10.0:
                            continue
                        elif cap_filter_opt == "中大型股 (股本 >= 50億)" and stock_cap < 50.0:
                            continue
                            
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
                            
                            # 💡 雙後綴自癒機制
                            try:
                                if ticker in st.session_state.yf_cache:
                                    hist = st.session_state.yf_cache[ticker]
                                else:
                                    hist = data_fetcher.fetch_historical_data_cached(ticker, period="6mo")
                                    if not hist.empty and len(hist) >= 20:
                                        st.session_state.yf_cache[ticker] = hist
                            except Exception:
                                ticker = f"{code}.TWO"
                                if ticker in st.session_state.yf_cache:
                                    hist = st.session_state.yf_cache[ticker]
                                else:
                                    hist = data_fetcher.fetch_historical_data_cached(ticker, period="6mo")
                                    if not hist.empty and len(hist) >= 20:
                                        st.session_state.yf_cache[ticker] = hist
                                        
                            if hist.empty or len(hist) < 20:
                                continue
                            
                            is_box, box_amp = helpers.calculate_box_consolidation(hist, days=5, exclude_last_day=True)
                            if filter_box and not is_box:
                                continue
                                
                            if not is_code_etf:
                                try:
                                    stock = yf.Ticker(ticker, session=yf_session)
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
                                except Exception:
                                    pass
                                
                            hist['MA5'] = hist['Close'].rolling(5).mean()
                            hist['MA20'] = hist['Close'].rolling(20).mean()
                            latest = hist.iloc[-1]
                            
                            price = latest['Close']
                            pct_change_5d = 0.0
                            if len(hist) >= 6:
                                price_5d_ago = hist['Close'].iloc[-6]
                                if price_5d_ago > 0:
                                    pct_change_5d = ((price - price_5d_ago) / price_5d_ago) * 100
                            
                            is_momentum_stock = (pct_change_5d > 10.0) and (price > latest['MA5']) and (latest['MA5'] > latest['MA20'])
                            
                            if filter_momentum and not is_momentum_stock:
                                continue
                                
                            if pd.isna(price) or price <= 0:
                                continue
                    
                            ma5 = latest['MA5']
                            ma20 = latest['MA20']
                            
                            latest_vol = latest['Volume']
                            prev_20d_avg_vol = hist['Volume'].iloc[-21:-1].mean()
                            vol_ratio = latest_vol / prev_20d_avg_vol if prev_20d_avg_vol > 0 else 0.0
                            
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
                                "股本(億)": stock_cap if stock_cap > 0 else None,  # 💡 整合股本欄位
                                "漲跌幅(%)": round(pct_change, 2),
                                "最新單季EPS": latest_q_eps_val,
                                "去年年度EPS": latest_a_eps_val,
                                "月營收YoY/MoM": helpers.format_rev_growth(rev_item),
                                "外資金額(萬)": round(row_item['外資_張'] * price / 10, 1),
                                "投信金額(萬)": round(row_item['投信_張'] * price / 10, 1),
                                "自營金額(萬)": round(row_item['自營_張'] * price / 10, 1),
                                "分點買超明細": broker_details_str,
                                "融資餘額(張)": int(margin_data.get(code, {}).get("today", 0.0)),
                                "融資變動(張)": int(summary.loc[summary['證券代號'] == code, '融資_張'].values[0]),
                                "大戶比例": f"{round(tdcc_ratios.get(code, 0), 2)}%" if code in tdcc_ratios else "N/A",
                                "均線狀態": ma_status_display,
                                "前期箱型振幅": f"{box_amp}%" if is_box else f"{box_amp}% (未整理)",
                                "日K_MACD": macd_daily_status,
                                "60m_MACD": macd_60m_status,
                                "短期支壓(1M)": sr_1m,
                                "中期支壓(6M)": sr_6m,
                                "K線圖網址": f"https://tw.stock.yahoo.com/quote/{code}/technical-analysis"
                              })
                        except Exception:
                            yf_fail_count += 1
                            continue
                            
                if final_rows:
                    st.session_state.tab1_results = final_rows
                else:
                    st.session_state.tab1_results = []
                    # 💡 自動 API 連線故障診斷：只有當大比例（>70%）的股票都下載失敗時，才判定是 Yahoo API 阻擋 [1]
                    if yf_fail_count > len(top_candidates) * 0.7:
                        st.warning("⚠️ 偵測到 Yahoo Finance 數據伺服器目前對雲端伺服器進行了臨時頻率限制 (Error 429 - 請求過於頻繁)，導致所有候選股歷史 K 線下載失敗。建議您直接再次點擊上方「開始一鍵篩選股票」按鈕重試，或稍等 1-2 分鐘再試。")
                    else:
                        st.warning("查無符合篩選條件之個股。")

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
            
            st.success(f"篩選完成！共尋獲 {len(df_res)} 檔個股。")
            
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
            
            selected_rows = event.selection.rows
            if selected_rows:
                st.write("---")
                st.markdown("### 🎯 已選個股 - 主力分點進出特寫")
                for idx in selected_rows:
                    if idx >= len(df_res):  # 💡 安全越界保護 [1]
                        continue
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
                        
                        st.write("")
                        st.markdown("**🔥 全台所有分點 - 買賣超前 10 名排行 (不設限自選)：**")
                        with st.spinner(f"正在向系統調閱 {code} 的全台主力排行..."):
                            all_buyers, all_sellers = utils.fetch_stock_top_brokers_local(code, days=days_count)
                            
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
                    current_watchlist = utils.get_local_watchlist()
                    added_count = 0
                    for code in selected_codes:
                        if code not in current_watchlist:
                            current_watchlist.append(code)
                            added_count += 1
                    if added_count > 0:
                        utils.save_local_watchlist(current_watchlist)
                        st.success(f"已成功加入 {added_count} 檔股票至您的專屬自選股！")
                        time.sleep(0.8)
                        st.rerun()
                    else:
                        st.info("您選取的股票早已在自選股清單中囉！")
        else:
            st.warning("查無符合篩選條件之個股。")
