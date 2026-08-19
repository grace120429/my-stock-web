# tab4_etfs.py
import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
import data_fetcher
import storage
import utils

def render_tab4():
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
            
            yf_session_tab4 = utils.create_yf_session()
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
                
        html_cal = utils.render_streamlit_calendar(
            st.session_state.cal_year, 
            st.session_state.cal_month, 
            st.session_state.etf_events
        )
        st.markdown(html_cal, unsafe_allow_html=True)
        st.caption("提示：滑鼠懸停在紅色的除息日期上，可觀看當天除息 ETF 與金額詳情。")

    st.write("---")
    st.subheader("我的股息退休存錢筒 (複利配息計算機)")
    piggy_bank_data = utils.get_local_piggy_bank()
    
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
                    st.warning("請輸入有效的張數 or 股數！")
                else:
                    piggy_bank_data[p_code] = total_shares
                    utils.save_local_piggy_bank(piggy_bank_data)
                    st.success(f"持股已更新：{p_code} {p_zhang}張 {p_gu}股 (共 {total_shares} 張)")
                    time.sleep(0.5)
                    st.rerun()
                
        p_del = st.text_input("要移除的代號：", max_chars=6, key="pb_del")
        if st.button("移除持股"):
            p_del = p_del.upper().strip()
            if p_del in piggy_bank_data:
                del piggy_bank_data[p_del]
                utils.save_local_piggy_bank(piggy_bank_data)
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
                    
                # 💡 修正 Python and 語法 [1]
                if ex_month == st.session_state.cal_month and ex_year == st.session_state.cal_year:
                    total_selected_month_dividend += total_gu * latest_div_value
                
                pb_rows.append({
                    "代號": code,
                    "持股規格": shares_str,
                    "總股數": f"{total_gu:,} 股",
                    "現價": f"{round(price, 1)} 元",
                    "預估單股年配息": f"{current_year_sum_val} 元",
                    "預估年領股息": f"{utils.safe_int(est_annual):,} 元",
                    "持股市值": f"{utils.safe_int(market_val):,} 元"
                })
        if pb_rows:
            st.dataframe(pd.DataFrame(pb_rows), use_container_width=True)
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            col_stat1.metric("總持股市值", f"{utils.safe_int(total_market_value):,} 元")
            col_stat2.metric("預估年領總股息", f"{utils.safe_int(total_annual_dividend):,} 元")
            col_stat3.metric(
                f"{st.session_state.cal_month}月份預估配息收入", 
                f"{utils.safe_int(total_selected_month_dividend):,} 元",
                delta="該月份實際配息收入" if total_selected_month_dividend > 0 else "本月份無除息"
            )
        else:
            st.info("存錢筒目前無持股，請新增您的 ETF 持股比例。")