import os
import google.generativeai as genai
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime

# 配置能源
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel('gemini-1.5-flash')

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
    # 抓取來源：Google AI 官方部落格
    feed = feedparser.parse("https://blog.google/technology/ai/rss/")
    if feed.entries:
        entry = feed.entries[0]
        return entry.title, entry.link, entry.summary
    return None, None, None

def run_tower():
    title, link, summary = fetch_news()
    if not title: return

    prompt = f"{SYSTEM_PROMPT}\n\n裁決目標：\n標題：{title}\n內容：{summary}\n連結：{link}"
    response = model.generate_content(prompt)
    
    # 生成網頁模板 (#F4F1EA 質感)
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-Hant">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ background-color: #F4F1EA; color: #1a1a1a; font-family: serif; padding: 5% 10%; line-height: 1.8; }}
            h1 {{ border-bottom: 2px solid #000; padding-bottom: 10px; }}
            .judgment {{ white-space: pre-wrap; font-size: 1.1em; }}
            .footer {{ margin-top: 50px; font-size: 0.8em; color: #666; border-top: 1px solid #ccc; padding-top: 20px; }}
        </style>
        <title>BLACK TOWER - AI 裁決</title>
    </head>
    <body>
        <h1>BLACK TOWER：{title}</h1>
        <div class="judgment">{response.text}</div>
        <div class="footer">自動運行中 | <a href="{link}">原始連結</a> | 裁決時間：{datetime.now().strftime('%Y-%m-%d')}</div>
    </body>
    </html>
    """
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

if __name__ == "__main__":
    run_tower()
