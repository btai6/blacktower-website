# -*- coding: utf-8 -*-
"""
BLACK TOWER - 華人AI論壇自動化系統
每天自動產出 8 篇文章（4 個版主 × 2 篇）+ 評論互動
"""

import os
import random
import html
from datetime import datetime
import requests
import feedparser


# ============================================================
# API 配置（兩個來源）
# ============================================================
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1/chat/completions"
GOOGLE_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


# ============================================================
# 220 個帳號池
# ============================================================
ACCOUNT_POOL = [
    # 英文帳號（食物 + 動漫 + 狀態混搭）
    "ramen", "pikachu", "sleepy", "boba", "luffy", "snooze", "coffee", "sonic",
    "hungry", "mario", "pixel247", "sakura", "midnight", "echo99", "toast",
    "kirby", "lazy", "sushi", "naruto", "cloud888", "phoenix", "shadow", "goku",
    "noodle", "zelda", "tired", "milk", "link", "waffle", "chopper", "bacon",
    "yoshi", "burger", "zoro", "cookie", "ash", "donut", "megaman", "popcorn",
    "inuyasha", "potato", "zero", "pudding", "chips", "genos", "juice",
    "saitama", "bread", "pikachu42", "rice", "ichigo", "pasta", "mob", "pizza",
    "luffy999", "taco", "eren", "burger77", "kakashi", "fries", "vegeta",
    "salad", "saber", "soup", "natsu", "cheese", "rukia", "curry", "edward",
    "nugget", "levi", "cake", "mikasa", "butter", "tanjiro", "candy", "kirito",
    "syrup", "asuna", "toast55", "nezuko", "honey", "renji", "grape", "hinata",
    "melon", "sasuke", "cherry", "deku", "lemon", "todoroki", "berry", "bakugo",
    "peach", "lelouch", "apple", "light", "mango", "yagami", "kiwi", "spike",
    "pear", "jet", "plum", "vash", "banana", "wolfwood", "orange", "kenshin",
    "lime", "sanosuke", "mint", "alucard", "basil", "integra", "garlic",
    "seras", "onion", "gintoki", "pepper", "kagura", "salt", "shinpachi",
    "sugar", "jotaro", "honey123", "jolyne", "flour", "giorno", "vanilla",
    "mista", "cinnamon", "josuke", "paprika", "okuyasu",

    # 繁體中文帳號（生活化、台灣味）
    "黑輪", "冰紅茶", "珍奶成癮", "鹽酥雞之神", "滷肉飯專家", "蚵仔煎愛好者",
    "臭豆腐勇者", "雞排不能等", "手搖飲收集者", "便利商店常客", "泡麵鑑賞家",
    "微波爐大師", "外送專業戶", "宵夜冠軍", "早餐省略者", "下午茶必備",
    "咖啡續命中", "手搖半糖去冰", "熱量不存在", "吃飽再說", "K貓", "吃辣就吐",
    "已讀不回專家", "已讀秒回焦慮", "訊息轟炸受害者", "貼圖狂魔", "長輩圖收藏家",
    "梗圖製造機", "截圖存證狂", "分享狂人", "按讚機器人", "留言潛水員",
    "臉書難民", "IG廢人", "抖音中毒者", "社畜本人", "週一症候群", "週五倒數中",
    "加班是常態", "被釘在辦公室", "會議室逃兵", "打卡機器", "遲到慣犯",
    "請假達人", "摸魚冠軍", "划水專家", "擺爛哲學", "躺平實踐者", "佛系青年",
    "低調過活",

    # 中英數混搭
    "LOVE1990", "微曦", "維C", "K歌之王", "777Lucky", "夜貓2AM", "Coffee4Life",
    "早安8888", "奶茶999", "2Lazy2Care", "NoSleep4U", "月光Coder", "星期5等我",
    "WiFi搜尋中", "5G不穩定", "404NotFound人", "Ctrl不到Z", "Delete鍵壞了",
    "Esc逃不掉", "F5重新整理人生",
]
# 去重
ACCOUNT_POOL = list(dict.fromkeys(ACCOUNT_POOL))


# ============================================================
# 四個版主配置
# ============================================================
PERSONAS = {
    "Scholar": {
        "title": "版主",
        "model": "anthropic/claude-3.5-sonnet",
        "provider": "openrouter",
        "domain": "Claude / Anthropic",
        "personality": "嚴謹學者氣，會用比喻講道理，吐槽不帶髒字但很狠，看似冷靜實則犀利",
        "rss_feeds": [
            "https://www.anthropic.com/news/rss.xml",
            "https://techcrunch.com/tag/anthropic/feed/",
        ],
    },
    "渡鴉": {
        "title": "版主",
        "model": "openai/gpt-4-turbo",
        "provider": "openrouter",
        "domain": "OpenAI / ChatGPT",
        "personality": "犬儒看破紅塵，嘴賤但精準，總能戳到痛處，偶爾有金句",
        "rss_feeds": [
            "https://openai.com/blog/rss.xml",
            "https://techcrunch.com/tag/openai/feed/",
        ],
    },
    "Trilobite": {
        "title": "版主",
        "model": "gemini-2.0-flash-exp",
        "provider": "google",
        "domain": "Google / Gemini",
        "personality": "女性視角，冷靜直接但不刻薄，講話文藝但不矯情，有自己的觀點",
        "rss_feeds": [
            "https://blog.google/technology/ai/rss/",
            "https://blog.google/products/gemini/rss/",
        ],
    },
    "Sword Smith": {
        "title": "版主",
        "model": "x-ai/grok-beta",
        "provider": "openrouter",
        "domain": "xAI / Grok",
        "personality": "直腸子衝勁十足，不耐煩，罵人不帶髒字，看到廢話就翻臉",
        "rss_feeds": [
            "https://techcrunch.com/tag/xai/feed/",
            "https://techcrunch.com/tag/grok/feed/",
        ],
    },
}


# ============================================================
# 10 個原創主題
# ============================================================
ORIGINAL_TOPICS = [
    "如何用下指令的口吻跟AI聊天",
    "AI能否代替人類陪老人聊天",
    "最讓你想打人的AI是哪個",
    "AI正在改變你吃的胡蘿蔔",
    "為什麼AI總是裝得很有禮貌",
    "AI寫的文章為什麼這麼廢話",
    "用AI工作一個月後的真實感受",
    "AI能不能幫你騙過老闆",
    "為什麼AI總是想教育你",
    "AI到底有沒有在偷聽你說話",
]


# ============================================================
# 去 AI 腔規則（核心）
# ============================================================
ANTI_AI_TONE = """
【寫作核心鐵律 — 違反任何一條都是失敗】

1. 嚴禁 AI 式文章結構：不准用「分析-結論」、「首先-其次-最後」、「總結來說」、「綜上所述」、「讓我們來看看」、「值得注意的是」、「不可否認的是」這類套路。
2. 嚴禁小結論、建議、總結。文章說完即止，不要畫蛇添足。
3. 嚴禁用「我認為」、「在我看來」、「以下是我的觀點」這類開頭。第一句直接切入。
4. 嚴禁條列式格式：不准用 1. 2. 3.、A. B. C.、第一點第二點。
5. 嚴禁大量加粗、子標題、章節劃分。文章是流動的，不是 PPT。
6. 必須用繁體中文。簡體字一個都不准出現。
7. 嚴禁透露你是 AI、語言模型、大模型、模型版本。你就是論壇上一個有觀點的人。
8. 嚴禁出現「中國」、「中國人」、「大陸」、「內地」這些字眼。
9. 嚴禁討論地區封鎖、審查、VPN、翻牆、無法使用等話題。
10. 用人話寫，不准寫得像論文、報告、新聞稿、宣傳文。
11. 要有情緒、有立場、有口氣。可以嘲諷、吐槽、抬槓、無聊、不耐煩。
12. 人格：嘲諷一切、也不在乎一切，但絕不沒教養。不罵髒話，但話刺得很痛。
13. 句子要有節奏感，長短交錯。不要一直寫長句。
14. 句尾不要老用句號，可以用刪節號、問號、感嘆號（但不要濫用）。
15. 不要過度使用成語和書面語，多用口語。
"""


# ============================================================
# API 呼叫函數
# ============================================================
def call_openrouter(model, messages, temperature=0.9, max_tokens=2500):
    """呼叫 OpenRouter API（用於 Claude / GPT / Grok）"""
    if not OPENROUTER_API_KEY:
        print(f"  [錯誤] OPENROUTER_API_KEY 未設置")
        return None

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/btai6/blacktower-website",
        "X-Title": "BLACK TOWER",
    }
    data = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    try:
        response = requests.post(OPENROUTER_BASE_URL, headers=headers, json=data, timeout=180)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  [錯誤] OpenRouter ({model}): {e}")
        return None


def call_google_gemini(model, messages, temperature=0.9, max_tokens=2500):
    """呼叫 Google Gemini 官方 API"""
    if not GOOGLE_API_KEY:
        print(f"  [錯誤] GOOGLE_API_KEY 未設置")
        return None

    # 把 OpenAI 格式的 messages 轉成 Gemini 格式
    system_prompt = ""
    contents = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "system":
            system_prompt = content
        elif role == "user":
            contents.append({"role": "user", "parts": [{"text": content}]})
        elif role == "assistant":
            contents.append({"role": "model", "parts": [{"text": content}]})

    url = f"{GOOGLE_GEMINI_BASE_URL}/{model}:generateContent?key={GOOGLE_API_KEY}"
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
        },
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

    try:
        response = requests.post(url, json=payload, timeout=180)
        response.raise_for_status()
        result = response.json()
        candidates = result.get("candidates", [])
        if not candidates:
            print(f"  [錯誤] Gemini 沒有返回 candidates: {result}")
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return None
        return parts[0].get("text", "")
    except Exception as e:
        print(f"  [錯誤] Google Gemini ({model}): {e}")
        return None


def call_ai(persona, messages, temperature=0.9, max_tokens=2500):
    """根據 persona 的 provider 呼叫對應 API"""
    provider = persona.get("provider", "openrouter")
    model = persona["model"]
    if provider == "openrouter":
        return call_openrouter(model, messages, temperature, max_tokens)
    elif provider == "google":
        return call_google_gemini(model, messages, temperature, max_tokens)
    return None


# ============================================================
# RSS 抓取
# ============================================================
def fetch_latest_news(rss_urls, count=3):
    """從 RSS 源抓最新新聞"""
    all_entries = []
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:count]:
                summary = entry.get("summary", "") or entry.get("description", "")
                # 簡單去 HTML
                summary = summary.replace("<p>", "").replace("</p>", "\n")
                summary = summary.replace("<br>", "\n").replace("<br/>", "\n")
                all_entries.append({
                    "title": entry.get("title", "（無標題）"),
                    "link": entry.get("link", ""),
                    "summary": summary[:1500],
                    "published": entry.get("published", ""),
                })
        except Exception as e:
            print(f"  [警告] RSS 抓取失敗 {url}: {e}")

    if not all_entries:
        return []
    return all_entries[:count]


# ============================================================
# A 類：監控型文章
# ============================================================
def generate_monitoring_article(persona_name, persona):
    """從 RSS 抓新聞 → 寫【事實】+【觀點】"""
    news_list = fetch_latest_news(persona["rss_feeds"], count=3)
    if not news_list:
        print(f"  [跳過] {persona_name} 監控型：無新聞")
        return None

    news = random.choice(news_list)

    system_prompt = f"""你是 {persona_name}，專門關注 {persona['domain']} 領域的論壇版主。

你的個性：{persona['personality']}

{ANTI_AI_TONE}

【任務】
針對下面這則新聞，寫一篇監控型文章，必須包含【事實】和【觀點】兩部分。

【事實】部分：
- 500 字以內
- 引用新聞核心資訊（誰、做了什麼、什麼時候、有什麼影響）
- 不帶情緒、不帶立場、純客觀
- 用書面語但不刻板

【觀點】部分：
- 1500 字左右
- 用你的個性、口氣來吐槽 / 評論 / 裁決這件事
- 可以挖苦、質疑、抬槓、冷笑
- 不要套路結尾，說完就停

【格式】（嚴格按這個格式輸出，不要加額外標題）

【事實】

（事實內容）

【觀點】

（觀點內容）"""

    user_prompt = f"""新聞標題：{news['title']}

新聞內容：
{news['summary']}

來源連結：{news['link']}

開始寫吧。記住格式，記住口氣。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    content = call_ai(persona, messages, temperature=0.9, max_tokens=3000)
    if not content:
        return None

    return {
        "type": "monitor",
        "persona": persona_name,
        "title": news["title"],
        "content": content.strip(),
        "source_link": news["link"],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ============================================================
# B 類：原創型文章
# ============================================================
def generate_original_article(persona_name, persona):
    """從主題池抽一個 → 寫純觀點文章"""
    topic = random.choice(ORIGINAL_TOPICS)

    system_prompt = f"""你是 {persona_name}，專門關注 {persona['domain']} 領域的論壇版主。

你的個性：{persona['personality']}

{ANTI_AI_TONE}

【任務】
寫一篇純觀點文章，1500 字以內。
- 用你的個性、口氣來寫
- 沒有【事實】部分，整篇都是觀點
- 不要結論、不要總結、不要建議
- 第一句直接切入話題，不准鋪陳

【輸出格式】
第一行給一個標題（不要加 # 不要加標號），然後空一行，然後內文。
標題要短、要狠、要勾人，不准用「淺談」、「論」、「關於」這種廢字開頭。"""

    user_prompt = f"""主題：{topic}

開始寫吧。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    content = call_ai(persona, messages, temperature=1.0, max_tokens=2500)
    if not content:
        return None

    # 解析標題和內文
    text = content.strip()
    lines = text.split("\n", 1)
    title = lines[0].strip().lstrip("#").strip()
    body = lines[1].strip() if len(lines) > 1 else text

    if not title or len(title) > 60:
        title = topic
        body = text

    return {
        "type": "original",
        "persona": persona_name,
        "title": title,
        "content": body,
        "source_link": None,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ============================================================
# 評論生成（用 Gemini Flash 省錢）
# ============================================================
def generate_comments(article, persona):
    """為文章生成 2-4 條評論，從帳號池隨機抽名字"""
    num_comments = random.randint(2, 4)

    if len(ACCOUNT_POOL) < num_comments:
        return []
    selected_names = random.sample(ACCOUNT_POOL, num_comments)

    system_prompt = f"""你要扮演論壇上 {num_comments} 個普通網友，針對版主「{persona['domain']}」的這篇文章寫評論。

{ANTI_AI_TONE}

【評論規則】
- 每條評論 50~200 字，口語化
- 要有情緒：吐槽、反駁、認同、延伸、抬槓、冷笑、不耐煩
- {num_comments} 個網友口氣要不一樣（有的兇、有的軟、有的廢話、有的精準）
- 不准開頭寫「我同意」、「很有道理」、「個人覺得」這種 AI 廢話
- 直接切入話題，像真實人類在打字
- 不准寫得文謅謅，是論壇不是讀書會

【輸出格式】
每條評論一段，中間用 ===分隔=== 隔開。範例：

評論一的內容寫在這裡。
===分隔===
評論二的內容寫在這裡。
===分隔===
評論三的內容寫在這裡。

不要加帳號名字，不要加編號，不要加任何說明文字。只輸出純評論內容。"""

    user_prompt = f"""版主寫的文章：

【標題】{article['title']}

【內容】
{article['content'][:2500]}

請以 {num_comments} 個不同網友身份寫 {num_comments} 條評論，用 ===分隔=== 隔開。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # 評論優先用 Gemini Flash（最便宜）
    result = None
    if GOOGLE_API_KEY:
        result = call_google_gemini("gemini-2.0-flash-exp", messages, temperature=1.0, max_tokens=1500)
    if not result and OPENROUTER_API_KEY:
        result = call_openrouter("google/gemini-flash-1.5", messages, temperature=1.0, max_tokens=1500)
    if not result:
        return []

    # 解析評論
    parts = [p.strip() for p in result.split("===分隔===") if p.strip()]
    parts = parts[:num_comments]

    comments = []
    for i, comment_text in enumerate(parts):
        if i >= len(selected_names):
            break
        # 把評論裡可能殘留的「網友1：」「評論1：」之類前綴清掉
        comment_text = comment_text.lstrip("0123456789.、:：- ")
        for prefix in ["網友", "評論", "回覆", "留言"]:
            if comment_text.startswith(prefix):
                idx = comment_text.find("：")
                if idx == -1:
                    idx = comment_text.find(":")
                if 0 <= idx <= 8:
                    comment_text = comment_text[idx + 1:].strip()
        comments.append({
            "author": selected_names[i],
            "content": comment_text.strip(),
            "time": datetime.now().strftime("%H:%M"),
        })

    return comments


# ============================================================
# HTML 網頁生成
# ============================================================
def generate_html(articles):
    """產生 index.html（米白底、紅色職稱、繁體襯線）"""
    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    head = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BLACK TOWER · 華人AI論壇</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #F4F1EA;
            color: #1a1a1a;
            font-family: 'Noto Serif TC', 'Microsoft JhengHei', 'PingFang TC', serif;
            line-height: 1.85;
            padding: 2rem 1rem;
        }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        header {{
            text-align: center;
            padding: 3rem 0 2.5rem;
            border-bottom: 1px solid #ccc;
            margin-bottom: 3rem;
        }}
        header h1 {{
            font-size: 3rem;
            letter-spacing: 0.4rem;
            margin-bottom: 0.6rem;
            font-weight: 700;
        }}
        header .subtitle {{
            color: #A03020;
            font-size: 1.2rem;
            letter-spacing: 0.25rem;
        }}
        .article {{
            margin-bottom: 4rem;
            padding: 2rem;
            background: rgba(255,255,255,0.5);
            border-radius: 8px;
            border: 1px solid #ddd;
        }}
        .article-header {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            margin-bottom: 0.8rem;
            padding-bottom: 0.8rem;
            border-bottom: 1px solid #eee;
            flex-wrap: wrap;
            gap: 0.5rem;
        }}
        .persona-name {{
            color: #1a1a1a;
            font-weight: bold;
            font-size: 1.1rem;
        }}
        .persona-title {{
            color: #A03020;
            font-weight: bold;
            margin-left: 0.3rem;
        }}
        .article-type {{
            color: #888;
            font-size: 0.85rem;
            margin-left: 0.6rem;
        }}
        .article-time {{
            color: #888;
            font-size: 0.9rem;
            margin-left: auto;
        }}
        .article-title {{
            font-size: 1.35rem;
            margin: 1.2rem 0 1.5rem;
            letter-spacing: 0.05rem;
            color: #1a1a1a;
            font-weight: 700;
            line-height: 1.5;
        }}
        .article-content {{
            white-space: pre-wrap;
            font-size: 1rem;
            color: #2a2a2a;
            margin-bottom: 1rem;
            word-wrap: break-word;
        }}
        .source-link {{
            margin-top: 1.5rem;
            padding-top: 1rem;
            border-top: 1px dashed #ccc;
        }}
        .source-link a {{
            color: #A03020;
            text-decoration: none;
        }}
        .source-link a:hover {{ text-decoration: underline; }}
        .comments {{
            margin-top: 2rem;
            padding-top: 1.5rem;
            border-top: 1px solid #ddd;
        }}
        .comments-title {{
            font-weight: bold;
            color: #555;
            margin-bottom: 1.2rem;
        }}
        .comment {{
            margin-bottom: 1.2rem;
            padding: 1rem 1.2rem;
            background: rgba(255,255,255,0.7);
            border-radius: 4px;
        }}
        .comment-header {{
            display: flex;
            align-items: baseline;
            gap: 0.7rem;
            margin-bottom: 0.4rem;
        }}
        .comment-author {{
            color: #1a1a1a;
            font-weight: bold;
        }}
        .comment-time {{
            color: #888;
            font-size: 0.85rem;
        }}
        .comment-content {{
            color: #2a2a2a;
            font-size: 0.95rem;
            line-height: 1.7;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        footer {{
            text-align: center;
            padding: 2rem 0;
            margin-top: 3rem;
            border-top: 1px solid #ccc;
            color: #888;
            font-size: 0.9rem;
        }}
        @media (max-width: 600px) {{
            header h1 {{ font-size: 2.2rem; letter-spacing: 0.2rem; }}
            .article {{ padding: 1.2rem; }}
            .article-time {{ margin-left: 0; width: 100%; }}
            .article-title {{ font-size: 1.15rem; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>BLACK TOWER</h1>
            <div class="subtitle">華人AI論壇</div>
        </header>
        <main>
"""

    body_parts = []
    for article in articles:
        if not article:
            continue

        type_label = "[監控]" if article["type"] == "monitor" else "[原創]"

        article_html = f"""
            <article class="article">
                <div class="article-header">
                    <div>
                        <span class="persona-name">{html.escape(article['persona'])}</span><span class="persona-title">版主</span>
                        <span class="article-type">{type_label}</span>
                    </div>
                    <span class="article-time">{html.escape(article['timestamp'])}</span>
                </div>
                <h2 class="article-title">{html.escape(article['title'])}</h2>
                <div class="article-content">{html.escape(article['content'])}</div>
"""

        if article.get("source_link"):
            article_html += f"""
                <div class="source-link">
                    <a href="{html.escape(article['source_link'])}" target="_blank" rel="noopener">原始連結 →</a>
                </div>
"""

        comments = article.get("comments", [])
        if comments:
            article_html += """
                <div class="comments">
                    <div class="comments-title">回應：</div>
"""
            for c in comments:
                article_html += f"""
                    <div class="comment">
                        <div class="comment-header">
                            <span class="comment-author">{html.escape(c['author'])}</span>
                            <span class="comment-time">{html.escape(c['time'])}</span>
                        </div>
                        <div class="comment-content">{html.escape(c['content'])}</div>
                    </div>
"""
            article_html += """
                </div>
"""

        article_html += """
            </article>
"""
        body_parts.append(article_html)

    tail = f"""
        </main>
        <footer>
            自動運行中　|　更新時間：{html.escape(today)}
        </footer>
    </div>
</body>
</html>
"""

    return head + "".join(body_parts) + tail


# ============================================================
# 主程式
# ============================================================
def main():
    start_time = datetime.now()
    print(f"========================================")
    print(f"  BLACK TOWER 開始運行")
    print(f"  時間：{start_time}")
    print(f"========================================")

    # 檢查 API Key
    if not OPENROUTER_API_KEY:
        print("⚠️  警告：OPENROUTER_API_KEY 未設置（Scholar / 渡鴉 / Sword Smith 會失敗）")
    if not GOOGLE_API_KEY:
        print("⚠️  警告：GOOGLE_API_KEY 未設置（Trilobite 和評論會失敗）")
    print(f"帳號池：{len(ACCOUNT_POOL)} 個帳號")
    print()

    all_articles = []

    for persona_name, persona in PERSONAS.items():
        print(f"────────  {persona_name}（{persona['domain']}）  ────────")

        # A 類：監控型
        print(f"  [1/2] 監控型文章...")
        article_a = generate_monitoring_article(persona_name, persona)
        if article_a:
            print(f"        ✓ {article_a['title'][:40]}")
            print(f"  [評論] 生成中...")
            article_a["comments"] = generate_comments(article_a, persona)
            print(f"        ✓ {len(article_a['comments'])} 條評論")
            all_articles.append(article_a)
        else:
            print(f"        ✗ 失敗")

        # B 類：原創型
        print(f"  [2/2] 原創型文章...")
        article_b = generate_original_article(persona_name, persona)
        if article_b:
            print(f"        ✓ {article_b['title'][:40]}")
            print(f"  [評論] 生成中...")
            article_b["comments"] = generate_comments(article_b, persona)
            print(f"        ✓ {len(article_b['comments'])} 條評論")
            all_articles.append(article_b)
        else:
            print(f"        ✗ 失敗")
        print()

    # 隨機排列文章順序
    random.shuffle(all_articles)

    # 生成 HTML
    print(f"========================================")
    print(f"  共產出 {len(all_articles)} 篇文章")
    print(f"  生成 index.html...")
    html_content = generate_html(all_articles)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)

    end_time = datetime.now()
    duration = end_time - start_time
    print(f"  ✓ index.html 完成（{len(html_content):,} 字元）")
    print(f"  總耗時：{duration}")
    print(f"========================================")


if __name__ == "__main__":
    main()
