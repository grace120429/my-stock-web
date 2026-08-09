# config.py
import ssl
import urllib3
import requests as std_requests

# ==================== 全域繞過 Python 的 SSL 憑證安全驗證 ====================
try:
    ssl._create_default_https_context = ssl._create_unverified_context
except AttributeError:
    pass

# 關閉跳過 SSL 憑證驗證時產生的安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==================== 最新版 yfinance / curl_cffi 專用 Session 建立 ====================
try:
    # 優先嘗試載入 curl_cffi 以模擬瀏覽器特徵，減少被證交所阻擋的機率
    from curl_cffi import requests as curl_requests
    unsafe_session = curl_requests.Session(impersonate="chrome")
    unsafe_session.verify = False
except ImportError:
    # 若未安裝 curl_cffi，則自動降級使用標準 requests
    unsafe_session = std_requests.Session()
    unsafe_session.verify = False