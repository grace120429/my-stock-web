# tab3_brokers.py
import streamlit as st
import pandas as pd
import data_fetcher
import storage

def render_tab3(brokers_dict):
    st.subheader("特寫分點主力特定天數交易明細")
    
    with st.expander("管理我的自訂券商分點"):
        col_b1, col_b2 = st.columns(2)
        new_b_name = col_b1.text_input("分點名稱 (如: 凱基台北)：")
        new_b_code = col_b2.text_input("分點代號 (4碼，如: 9268)：")
        if st.button("儲存新分點"):
            if new_b_name and new_b_code:
                brokers_dict[new_b_name] = new_b_code.upper()
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
            st.write("")
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