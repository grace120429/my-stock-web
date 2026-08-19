# tab5_comments.py
import streamlit as st
import time
from datetime import datetime, timezone, timedelta

# 💡 安全重定向引進 [1]
import app_utils as utils

def render_tab5():
    st.subheader("💬 讀者交流留言區")
    comments = utils.load_comments()
    
    with st.form("comment_form", clear_on_submit=True):
        col_author, col_submit = st.columns([1, 3])
        author_name = col_author.text_input("您的稱呼：", max_chars=10, value="匿名讀者")
        comment_content = st.text_area("留言內容：", max_chars=200, placeholder="歡迎在這裡分享您的想法 or 回饋...")
        submitted = st.form_submit_button("送出留言")
        
        if submitted:
            if not comment_content.strip():
                st.warning("請填寫留言內容！")
            else:
                new_comment = {
                    "id": int(time.time() * 1000),
                    "time": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
                    "author": author_name.strip() if author_name.strip() else "匿名讀者",
                    "content": comment_content.strip(),
                    "reply": "",
                    "reply_time": ""
                }
                comments.append(new_comment)
                utils.save_comments(comments)
                st.success("留言發表成功！")
                time.sleep(0.5)
                st.rerun()
                
    st.write("---")
    st.write(f"目前共有 {len(comments)} 條留言：")
    
    if not comments:
        st.info("目前尚無留言，歡迎成為第一個留言的人！")
    else:
        for msg in reversed(comments):
            reply_html = ""
            if "reply" in msg and msg["reply"]:
                reply_time_str = f" <span style='color: gray; font-size: 11px; margin-left: 10px;'>({msg.get('reply_time', '')})</span>" if msg.get('reply_time') else ""
                reply_html = f"""
                <div style='background-color: #eef1f6; padding: 10px; border-radius: 6px; margin-top: 10px; border-left: 3px solid #0056b3; margin-left: 15px;'>
                    <span style='font-weight: bold; color: #0056b3;'>版主回覆：</span>{reply_time_str}
                    <p style='margin-top: 5px; color: #444; font-size: 13px; white-space: pre-wrap; margin-bottom: 0;'>{msg['reply']}</p>
                </div>
                """
                
            st.markdown(
                f"""
                <div style='background-color: #f8f9fa; padding: 12px; border-radius: 8px; margin-bottom: 10px; border-left: 5px solid #007bff;'>
                    <span style='font-weight: bold; color: #333;'>{msg['author']}</span> 
                    <span style='color: gray; font-size: 11px; margin-left: 10px;'>{msg['time']}</span>
                    <p style='margin-top: 5px; color: #555; font-size: 14px; white-space: pre-wrap; margin-bottom: 5px;'>{msg['content']}</p>
                    {reply_html}
                </div>
                """, 
                unsafe_allow_html=True
            )
            
    st.write("---")
    with st.expander("🛠️ 留言板後台管理功能"):
        admin_pwd = st.text_input("請輸入管理員密碼：", type="password", key="admin_pwd_input")
        
        if admin_pwd == "admin888":
            st.success("身分驗證成功！已開啟管理權限。")
            st.write("### 📢 編輯側邊欄公告")
            current_ann = utils.load_announcement()
            new_ann_text = st.text_area(
                "請輸入公告內容（支援多行輸入，可用來發布每日精選標的等）：",
                value=current_ann.get("content", ""),
                height=150,
                help="儲存後，所有造訪本網頁的人都會立刻在側邊欄看到此公告內容。"
            )
            if st.button("儲存並發布公告", type="primary", key="save_ann_btn_tab5"):
                updated_ann = {
                    "content": new_ann_text.strip(),
                    "date": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
                }
                utils.save_announcement(updated_ann)
                st.success("公告已成功儲存並同步發布至側邊欄！")
                time.sleep(0.5)
                st.rerun()
                
            st.write("---")
            if not comments:
                st.info("目前沒有留言可供管理。")
            else:
                st.write("### 留言管理與回復面板")
                for msg in comments:
                    st.write("---")
                    col_msg_info, col_del_btn = st.columns([5, 1])
                    col_msg_info.markdown(f"**【{msg['author']}】** ({msg['time']}):  \n{msg['content']}")
                    
                    if col_del_btn.button("刪除此留言", key=f"del_{msg['id']}", type="secondary"):
                        comments = [c for c in comments if c["id"] != msg["id"]]
                        utils.save_comments(comments)
                        st.success("留言已順利刪除！")
                        time.sleep(0.5)
                        st.rerun()
                        
                    has_reply = "reply" in msg and msg["reply"]
                    if has_reply:
                        st.info(f"當前已回覆：{msg['reply']} ({msg.get('reply_time', '')})")
                        
                    reply_input = st.text_input(
                        "回覆此留言：" if not has_reply else "修改回覆內容：",
                        value=msg.get("reply", ""),
                        key=f"rep_input_{msg['id']}"
                    )
                    
                    col_rep_btn1, col_rep_btn2 = st.columns([1.5, 4])
                    
                    if col_rep_btn1.button("送出/修改回覆", key=f"rep_btn_{msg['id']}", type="primary"):
                        if reply_input.strip():
                            for c in comments:
                                if c["id"] == msg["id"]:
                                    c["reply"] = reply_input.strip()
                                    c["reply_time"] = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
                                    break
                            utils.save_comments(comments)
                            st.success("回覆送出成功！")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.warning("請填寫回覆內容！")
                            
                    if has_reply and col_rep_btn2.button("刪除此回覆", key=f"rep_del_{msg['id']}", type="secondary"):
                        for c in comments:
                            if c["id"] == msg["id"]:
                                c["reply"] = ""
                                c["reply_time"] = ""
                                break
                        utils.save_comments(comments)
                        st.success("已清除回覆！")
                        time.sleep(0.5)
                        st.rerun()
                        
        elif admin_pwd:
            st.error("密碼輸入錯誤，請重新確認！")
