def render_streamlit_calendar(year, month, events):
    import calendar
    cal = calendar.Calendar(calendar.SUNDAY)
    month_days = cal.monthdayscalendar(year, month)
    
    # 星期標頭
    headers = ["日", "一", "二", "三", "四", "五", "六"]
    header_html = "".join([f"<th class='cal-cell cal-header'>{h}</th>" for h in headers])
    
    rows_html = []
    for week in month_days:
        row_cells = []
        for day in week:
            if day == 0:
                row_cells.append("<td class='cal-cell cal-empty'></td>")
            else:
                target_date = datetime(year, month, day).date()
                day_events = events.get(target_date, [])
                
                if day_events:
                    # 使用 HTML 實體 &#13; 實現 Tooltip 多行換行顯示 (保持簡潔風格)
                    tooltip_text = f"除息預告 ({year}/{month:02d}/{day:02d})：&#13;" + "&#13;".join([f"{ev['code']} {ev['name']}: {ev['amount']}" for ev in day_events])
                    row_cells.append(
                        f"<td class='cal-cell cal-event' title='{tooltip_text}'>{day}</td>"
                    )
                else:
                    now_tw = datetime.now(timezone(timedelta(hours=8))).date()
                    if target_date == now_tw:
                        row_cells.append(f"<td class='cal-cell cal-today'>{day}</td>")
                    else:
                        row_cells.append(f"<td class='cal-cell cal-normal'>{day}</td>")
        rows_html.append(f"<tr class='cal-row'>{''.join(row_cells)}</tr>")
        
    style_css = """
    <style>
    .cal-table {
        display: table !important;
        width: 100% !important;
        border-collapse: collapse !important;
        table-layout: fixed !important;
        font-family: sans-serif;
    }
    .cal-row {
        display: table-row !important;
    }
    .cal-cell {
        display: table-cell !important;
        width: 14.28% !important;
        height: 45px !important;
        text-align: center !important;
        vertical-align: middle !important;
        border: 1px solid #e6e9ef !important;
        font-size: 14px !important;
        padding: 0 !important;
        box-sizing: border-box !important;
    }
    .cal-header {
        font-weight: bold !important;
        background-color: #f0f2f6 !important;
        padding: 6px 0 !important;
    }
    .cal-empty {
        background-color: transparent !important;
    }
    .cal-normal {
        background-color: transparent !important;
    }
    .cal-today {
        background-color: #007bff !important;
        color: white !important;
        font-weight: bold !important;
    }
    .cal-event {
        background-color: #ffcccc !important;
        color: #cc0000 !important;
        font-weight: bold !important;
        cursor: pointer !important;
    }
    </style>
    """
    
    html_table = f"""
    {style_css}
    <table class='cal-table'>
        <thead><tr class='cal-row'>{header_html}</tr></thead>
        <tbody>{''.join(rows_html)}</tbody>
    </table>
    """
    
    # 💡 核心優化：去除所有換行符與縮排空格，防止 Streamlit Markdown 引擎將其誤判為階梯排版！
    return html_table.replace('\n', '').replace('\r', '').replace('  ', '')
