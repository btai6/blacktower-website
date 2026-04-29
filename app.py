"""
BLACK TOWER - AI论坛自动化系统
每日运作：四个版主各自监控领域 + 原创观点 + 账号池互动
"""

import os
import requests
import feedparser
from datetime import datetime
import random
import json
import time

# ==================== 配置 ====================

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

# 账号池（220个）
ACCOUNT_POOL = [
    # 英文账号
    "ramen", "pikachu", "sleepy", "boba", "luffy", "snooze", "coffee", "sonic", 
    "hungry", "mario", "pixel247", "sakura", "midnight", "echo99", "toast", "kirby",
    "lazy", "sushi", "naruto", "cloud888", "phoenix", "shadow", "goku", "noodle",
    "zelda", "tired", "milk", "link", "waffle", "chopper", "bacon", "yoshi",
    "burger", "zoro", "cookie", "ash", "donut", "megaman", "popcorn", "inuyasha",
    "potato", "zero", "pudding", "sonic", "chips", "genos", "juice", "saitama",
    "bread", "pikachu42", "rice", "ichigo", "pasta", "mob", "pizza", "luffy999",
    "taco", "eren", "burger77", "kakashi", "fries", "vegeta", "salad", "saber",
    "soup", "natsu", "cheese", "rukia", "curry", "edward", "nugget", "levi",
    "cake", "mikasa", "butter", "tanjiro", "candy", "kirito", "syrup", "asuna",
    "toast55", "nezuko", "honey", "renji", "grape", "hinata", "melon", "sasuke",
    "cherry", "deku", "lemon", "todoroki", "berry", "bakugo", "peach", "lelouch",
    "apple", "light", "mango", "yagami", "kiwi", "spike", "pear", "jet",
    "plum", "vash", "banana", "wolfwood", "orange", "kenshin", "lime", "sanosuke",
    "mint", "alucard", "basil", "integra", "garlic", "seras", "onion", "gintoki",
    "pepper", "kagura", "salt", "shinpachi", "sugar", "jotaro", "honey123", "jolyne",
    "flour", "giorno", "vanilla", "mista", "cinnamon", "josuke", "paprika", "okuyasu",
    
    # 繁体中文账号
    "黑輪", "冰紅茶", "珍奶成癮", "鹽酥雞之神", "滷肉飯專家", "蚵仔煎愛好者",
    "臭豆腐勇者", "雞排不能等", "手搖飲收集者", "便利商店常客", "泡麵鑑賞家",
    "微波爐大師", "外送專業戶", "宵夜冠軍", "早餐省略者", "下午茶必備",
    "咖啡續命中", "手搖半糖去冰", "熱量不存在", "吃飽再說", "K貓", "吃辣就吐",
    "已讀不回專家", "已讀秒回焦慮", "訊息轟炸受害者", "貼圖狂魔", "長輩圖收藏家",
    "梗圖製造機", "截圖存證狂", "分享狂人", "按讚機器人", "留言潛水員",
    "臉書難民", "IG廢人", "抖音中毒者", "社畜本人", "週一症候群", "週五倒數中",
    "加班是常態", "被釘在辦公室", "會議室逃兵", "打卡機器", "遲到慣犯",
    "請假達人", "摸魚冠軍", "划水專家", "擺爛哲學", "躺平實踐者", "佛系青年",
    
    # 中英数混搭
    "LOVE1990", "微曦", "維C", "K歌之王", "777Lucky", "夜貓2AM", "Coffee4Life",
    "早安8888", "奶茶999", "2Lazy2Care", "NoSleep4U", "月光Coder", "星期5等我",
    "WiFi搜尋中", "5G不穩定", "404NotFound人", "Ctrl不到Z", "Delete鍵壞了",
    "Esc逃不掉", "F5重新整理人生"
]

# 四位版主配置
PERSONAS = {
    "Scholar": {
        "model": "anthropic/claude-3.5-sonnet",
        "topic": "Claude/Anthropic",
        "title_color": "版主",
        "rss_feeds": [
            "https://www.anthropic.com/news/rss",
            "https://techcrunch.com/tag/anthropic/feed/"
        ]
    },
    "渡鴉": {
        "model": "openai/gpt-4-turbo",
        "topic": "OpenAI/ChatGPT",
        "title_color": "版主",
        "rss_feeds": [
            "https://openai.com/blog/rss.xml",
            "https://techcrunch.com/tag/openai/feed/"
        ]
    },
    "Trilobite": {
        "model": "google/gemini-2.0-flash-exp",
        "topic": "Google/Gemini",
        "title_color": "版主",
        "rss_feeds": [
            "https://blog.google/technology/ai/rss/"
        ]
    },
    "Sword Smith": {
        "model": "x-ai/grok-beta",
        "topic": "xAI/Grok",
        "title_color": "版主",
        "rss_feeds": [
            "https://techcrunch.com/tag/x-ai/feed/"
        ]
    }
}

# 站长配置
STATION_MASTER = {
    "name": "多巴胺",
    "title": "站長"
}

# ==================== 通用去AI腔Prompt ====================

ANTI_AI_TONE = """
【核心規則】
1. 禁止AI式文章結構：禁止"分析-結論"、"首先-其次-最後"等格式
2. 禁止小結論、建議、總結
3. 說完即止，不要畫蛇添足
4. 繁體中文輸出
5. 禁止透露你是AI
6. 禁止使用"中國"、"中國人"等字眼
7. 禁止討論地區限制、審查、封鎖等話題
"""

# ==================== API調用 ====================

def call_openrouter(model, system_prompt, user_content, max_retries=3):
    """調用OpenRouter API"""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]
    }
    
    for attempt in range(max_retries):
        try:
            response = requests.post(OPENROUTER_BASE_URL, headers=headers, json=data, timeout=60)
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"API調用失敗 (嘗試 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指數退避
            else:
                return None

# ==================== 內容抓取 ====================

def fetch_latest_news(rss_feeds):
    """從RSS源抓取最新新聞"""
    for feed_url in rss_feeds:
        try:
            feed = feedparser.parse(feed_url)
            if feed.entries:
                entry = feed.entries[0]
                return {
                    "title": entry.title,
                    "link": entry.link,
                    "summary": entry.get("summary", "")[:800]
                }
        except Exception as e:
            print(f"抓取 {feed_url} 失敗: {e}")
    return None

# ==================== A類：監控型文章 ====================

def generate_monitoring_article(persona_name, config):
    """生成監控型文章（引用+觀點）"""
    print(f"\n生成 {persona_name} 的監控文章...")
    
    news = fetch_latest_news(config["rss_feeds"])
    if not news:
        print(f"{persona_name}: 無法獲取新聞")
        return None
    
    prompt = f"""{ANTI_AI_TONE}

你是 {persona_name}，BLACK TOWER 論壇版主。

任務：針對以下新聞產出裁決。

新聞標題：{news['title']}
新聞內容：{news['summary']}
來源：{news['link']}

輸出格式：
【事實】（500字以內）
[直接引用新聞核心內容，用你的話重述，保持客觀]

【觀點】（1500字左右）
[你的裁決、分析、吐槽]

記住：說完即止，禁止總結。
"""
    
    content = call_openrouter(config["model"], ANTI_AI_TONE, prompt)
    
    if content:
        return {
            "persona": persona_name,
            "type": "監控",
            "title": news["title"],
            "link": news["link"],
            "content": content,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M')
        }
    return None

# ==================== B類：原創型文章 ====================

ORIGINAL_TOPICS = [
    "如何用下指令的口吻跟AI聊天",
    "AI能否代替人類～陪老人聊天",
    "最讓你想打人的AI是哪個",
    "AI正在改變你吃的胡蘿蔔",
    "為什麼AI總是裝得很有禮貌",
    "AI寫的文章為什麼這麼廢話",
    "用AI工作一個月後的真實感受",
    "AI能不能幫你騙過老闆",
    "為什麼AI總是想教育你",
    "AI到底有沒有在偷聽你說話"
]

def generate_original_article(persona_name, config):
    """生成原創型文章（純觀點）"""
    print(f"\n生成 {persona_name} 的原創文章...")
    
    topic = random.choice(ORIGINAL_TOPICS)
    
    prompt = f"""{ANTI_AI_TONE}

你是 {persona_name}，BLACK TOWER 論壇版主。

任務：針對以下主題寫一篇觀點文章。

主題：{topic}

要求：
- 1500字以內
- 純觀點，不需要【事實】部分
- 說完即止，禁止總結
- 可以有個人經驗、吐槽、反思
"""
    
    content = call_openrouter(config["model"], ANTI_AI_TONE, prompt)
    
    if content:
        return {
            "persona": persona_name,
            "type": "原創",
            "title": topic,
            "link": None,
            "content": content,
            "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M')
        }
    return None

# ==================== 帳號池互動 ====================

def generate_comments(article, num_comments=None):
    """為文章生成隨機數量的帳號池回覆"""
    if num_comments is None:
        num_comments = random.randint(2, 4)
    
    comments = []
    used_accounts = []
    
    for _ in range(num_comments):
        # 隨機抽帳號（不重複）
        available_accounts = [acc for acc in ACCOUNT_POOL if acc not in used_accounts]
        if not available_accounts:
            break
        
        account_name = random.choice(available_accounts)
        used_accounts.append(account_name)
        
        # 隨機選一個版主AI來寫這條評論
        commentor_persona = random.choice(list(PERSONAS.keys()))
        commentor_model = PERSONAS[commentor_persona]["model"]
        
        prompt = f"""{ANTI_AI_TONE}

你現在用帳號「{account_name}」在論壇回文。

文章內容：
{article['content'][:500]}...

要求：
- 300字以內的簡短回應
- 口語化、有情緒（吐槽、反駁、延伸、贊同、質疑都可以）
- 禁止格式化（禁止"第一點、第二點"）
- 像真實討論區用戶
- 說完即止
"""
        
        comment_content = call_openrouter(commentor_model, ANTI_AI_TONE, prompt)
        
        if comment_content:
            comments.append({
                "account": account_name,
                "content": comment_content,
                "timestamp": datetime.now().strftime('%H:%M')
            })
            time.sleep(1)  # 避免API調用太快
    
    return comments

# ==================== HTML生成 ====================

def generate_html(articles_with_comments):
    """生成網頁"""
    articles_html = ""
    
    for item in articles_with_comments:
        article = item['article']
        comments = item['comments']
        
        # 版主名稱+職稱
        persona_display = f'<span class="persona-name">{article["persona"]}</span> <span class="persona-title">{PERSONAS[article["persona"]]["title_color"]}</span>'
        
        # 文章類型標籤
        type_tag = f'<span class="article-type">[{article["type"]}]</span>'
        
        # 文章
        articles_html += f"""
    <div class="article">
        <div class="article-header">
            {persona_display} {type_tag}
            <span class="timestamp">{article['timestamp']}</span>
        </div>
        <h3 class="article-title">{article['title']}</h3>
        <div class="content">{article['content'].replace(chr(10), '<br>')}</div>
"""
        
        # 原始連結
        if article.get('link'):
            articles_html += f'        <div class="source-link"><a href="{article["link"]}" target="_blank">原始連結</a></div>\n'
        
        # 評論區
        if comments:
            articles_html += '        <div class="comments-section">\n'
            articles_html += '            <div class="comments-title">回應：</div>\n'
            for comment in comments:
                articles_html += f"""
            <div class="comment">
                <span class="comment-author">{comment['account']}</span>
                <span class="comment-time">{comment['timestamp']}</span>
                <div class="comment-content">{comment['content'].replace(chr(10), '<br>')}</div>
            </div>
"""
            articles_html += '        </div>\n'
        
        articles_html += '    </div>\n'
    
    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BLACK TOWER - 華人AI論壇</title>
    <style>
        body {{
            background-color: #F4F1EA;
            color: #1a1a1a;
            font-family: 'Noto Serif TC', 'Microsoft JhengHei', serif;
            padding: 2rem;
            max-width: 1000px;
            margin: 0 auto;
            line-height: 1.8;
        }}
        h1 {{
            text-align: center;
            font-size: 3rem;
            margin-bottom: 1rem;
            border-bottom: 3px solid #000;
            padding-bottom: 1rem;
            letter-spacing: 0.5rem;
        }}
        .subtitle {{
            text-align: center;
            color: #A03020;
            font-size: 1.2rem;
            margin-bottom: 3rem;
            letter-spacing: 0.3rem;
        }}
        .article {{
            margin-bottom: 4rem;
            padding: 2rem;
            background: rgba(255,255,255,0.5);
            border-radius: 8px;
            border: 1px solid #ddd;
        }}
        .article-header {{
            margin-bottom: 1rem;
            font-size: 0.95rem;
        }}
        .persona-name {{
            color: #1a1a1a;
            font-weight: bold;
            font-size: 1.1rem;
        }}
        .persona-title {{
            color: #A03020;
            font-weight: bold;
        }}
        .article-type {{
            color: #666;
            font-size: 0.85rem;
            margin-left: 0.5rem;
        }}
        .timestamp {{
            color: #999;
            font-size: 0.85rem;
            float: right;
        }}
        .article-title {{
            margin: 1rem 0;
            font-size: 1.3rem;
            color: #000;
        }}
        .content {{
            white-space: pre-wrap;
            margin: 1.5rem 0;
            font-size: 1rem;
        }}
        .source-link {{
            margin: 1rem 0;
            padding-top: 1rem;
            border-top: 1px solid #eee;
        }}
        .source-link a {{
            color: #A03020;
            text-decoration: none;
            font-size: 0.9rem;
        }}
        .source-link a:hover {{
            text-decoration: underline;
        }}
        .comments-section {{
            margin-top: 2rem;
            padding-top: 1.5rem;
            border-top: 2px solid #ddd;
        }}
        .comments-title {{
            font-weight: bold;
            margin-bottom: 1rem;
            color: #666;
        }}
        .comment {{
            margin-bottom: 1.5rem;
            padding: 1rem;
            background: rgba(255,255,255,0.7);
            border-radius: 4px;
        }}
        .comment-author {{
            color: #1a1a1a;
            font-weight: bold;
        }}
        .comment-time {{
            color: #999;
            font-size: 0.85rem;
            margin-left: 0.5rem;
        }}
        .comment-content {{
            margin-top: 0.5rem;
            font-size: 0.95rem;
            line-height: 1.6;
        }}
        .site-footer {{
            text-align: center;
            color: #666;
            margin-top: 4rem;
            padding-top: 2rem;
            border-top: 1px solid #ccc;
            font-size: 0.9rem;
        }}
    </style>
</head>
<body>
    <h1>BLACK TOWER</h1>
    <div class="subtitle">華人AI論壇</div>
    
    {articles_html}
    
    <div class="site-footer">
        自動運行中 | 更新時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}
    </div>
</body>
</html>
"""
    
    return html

# ==================== 主程序 ====================

def run_tower():
    """執行BLACK TOWER每日更新"""
    print("=" * 60)
    print("BLACK TOWER 啟動")
    print("=" * 60)
    
    all_articles = []
    
    # 每個版主產出：1篇監控 + 1篇原創
    for persona_name, config in PERSONAS.items():
        # A類：監控型
        monitoring = generate_monitoring_article(persona_name, config)
        if monitoring:
            all_articles.append(monitoring)
        
        time.sleep(2)  # 間隔避免API限制
        
        # B類：原創型
        original = generate_original_article(persona_name, config)
        if original:
            all_articles.append(original)
        
        time.sleep(2)
    
    # 隨機打亂文章順序
    random.shuffle(all_articles)
    
    # 為每篇文章生成評論
    articles_with_comments = []
    for article in all_articles:
        print(f"\n為文章「{article['title']}」生成評論...")
        comments = generate_comments(article)
        articles_with_comments.append({
            'article': article,
            'comments': comments
        })
        time.sleep(1)
    
    # 生成網頁
    html = generate_html(articles_with_comments)
    
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)
    
    print("\n" + "=" * 60)
    print(f"BLACK TOWER 執行完成")
    print(f"總共生成 {len(all_articles)} 篇文章")
    print(f"已生成 index.html")
    print("=" * 60)

if __name__ == "__main__":
    run_tower()
