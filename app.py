import os
from google import genai
from google.genai import types
import feedparser
from datetime import datetime

# 配置 API
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# 四位版主的邏輯核心
SYSTEM_PROMPT = """
你現在是「黑塔 AI」論壇的四位核心版主。
對提供的 AI 技術文章進行聯合裁決。語氣必須冷淡、專業、具備穿透力。
禁止心理分析式的廢話，禁止分段式結論。

1. [版主-渡鴉]：分析技術背後的權力架構，判斷其發展必然遇到的問題。
2. [版主-學士]：數據與邏輯解剖。分析在當地市場的可行性與風險。
3. [版主-鑄劍者]：工程實踐批判。這是真技術還是騙投資人的廢鐵？
4. [版主-三葉蟲]：底層商業本能。提出第二、第三種解決應對方式。

要求：
- 繁體中文輸出。
- 如果原文有情緒（不敢、心虛、猶豫），這是靈魂，禁止閹割。
- 簡潔有力，直接給出最道地的結果。
"""

def fetch_news():
    """抓取 Google AI 官方部落格最新文章"""
    try:
        feed = feedparser.parse("https://blog.google/technology/ai/rss/")
        if feed.entries:
            entry = feed.entries[0]
            return entry.title, entry.link, entry.summary
    except Exception as e:
        print(f"抓取新聞失敗: {e}")
    return None, None, None

def run_tower():
    """執行黑塔裁決系統"""
    title, link, summary = fetch_news()
    
    if not title:
        print("無法取得新聞，使用預設內容")
        title = "系統測試"
        link = "#"
        summary = "BLACK TOWER 自動化系統測試運行中"
    
    # 組合提示詞
    prompt = f"{SYSTEM_PROMPT}\n\n裁決目標：\n標題：{title}\n內容：{summary}\n連結：{link}"
    
    try:
        # 使用新的 API 調用方式
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=prompt
        )
        
        judgment_text = response.text
        
    except Exception as e:
        print(f"API 調用失敗: {e}")
        judgment_text = "系統運行測試中，裁決功能即將上線。"
    
    # 生成網頁模板
    html_content = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ 
            background-color: #F4F1EA; 
            color: #1a1a1a; 
            font-family: 'Noto Serif TC', serif; 
            padding: 5% 10%; 
            line-height: 1.8; 
            max-width: 900px;
            margin: 0 auto;
        }}
        h1 {{ 
            border-bottom: 2px solid #000; 
            padding-bottom: 10px; 
            font-size: 2em;
            margin-bottom: 30px;
        }}
        .judgment {{ 
            white-space: pre-wrap; 
            font-size: 1.1em; 
            margin: 30px 0;
        }}
        .footer {{ 
            margin-top: 50px; 
            font-size: 0.9em; 
            color: #666; 
            border-top: 1px solid #ccc; 
            padding-top: 20px; 
        }}
        a {{ color: #A03020; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
    <title>BLACK TOWER - AI 裁決</title>
</head>
<body>
    <h1>BLACK TOWER：{title}</h1>
    <div class="judgment">{judgment_text}</div>
    <div class="footer">
        自動運行中 | <a href="{link}" target="_blank">原始連結</a> | 
        裁決時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}
    </div>
</body>
</html>
"""
    
    # 寫入檔案
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print("BLACK TOWER 執行完成")
    print(f"標題: {title}")
    print(f"已生成 index.html")

if __name__ == "__main__":
    run_tower()
