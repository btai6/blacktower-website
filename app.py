# -*- coding: utf-8 -*-
"""
BLACK TOWER - 華人AI論壇自動化系統
階段 2.1：雜誌風版面 + 影片・圖形獨立版 + SALON 禁地 + 防複製浮水印
- 6 分類首頁：Claude / ChatGPT / Gemini / Grok / 影片・圖形 / SALON
- 純前端 SPA：hash 路由、返回鍵、JS 即時搜尋（搜尋結果出現在跑馬燈下方）
- 跑馬燈：每 5 秒上下切換、輪播全站當天文章
- SALON 禁地頁：點進去顯示 ACCESS DENIED、會員限定
- 防複製半鎖：禁止選取，複製時自動加浮水印「來源：BLACK TOWER · btai6.github.io/blacktower-website」
- 全部使用 Google Gemini（免費 API）
- 四個版主用不同 system prompt 演不同個性
- A 類監控型：三塊拆解結構（事實 / 人味解讀 / 未來追問）
- B 類原創型：純觀點寫作
- C 類影片・圖形：四版主輪流寫感想（每天 1 篇）
- 人工題目庫（高優先級）
- 春秋筆法：不點名大陸 AI、不碰政治
"""

import os
import random
import html
import json
import time
from datetime import datetime, timedelta
import requests
import feedparser


def _random_comment_time():
    """評論時間隨機落在發文後 10 分鐘到 6 小時之間"""
    minutes_later = random.randint(10, 360)
    comment_dt = datetime.now() + timedelta(minutes=minutes_later)
    return comment_dt.strftime("%H:%M")


# ============================================================
# API 配置：只用 Google Gemini
# ============================================================
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# 主要使用免費實驗版 Flash
GEMINI_MODEL = "gemini-3-flash-preview"
# 備援模型
GEMINI_FALLBACK_MODEL = "gemini-3.1-flash-lite-preview"


# ============================================================
# 220 個帳號池
# ============================================================
ACCOUNT_POOL = [
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
    "LOVE1990", "微曦", "維C", "K歌之王", "777Lucky", "夜貓2AM", "Coffee4Life",
    "早安8888", "奶茶999", "2Lazy2Care", "NoSleep4U", "月光Coder", "星期5等我",
    "WiFi搜尋中", "5G不穩定", "404NotFound人", "Ctrl不到Z", "Delete鍵壞了",
    "Esc逃不掉", "F5重新整理人生",
]
ACCOUNT_POOL = list(dict.fromkeys(ACCOUNT_POOL))


# ============================================================
# 四個版主配置（全部走 Gemini，用 system prompt 區分個性）
# ============================================================
PERSONAS = {
    "Scholar": {
        "title": "版主",
        "domain": "Claude / Anthropic",
        "personality": (
            "嚴謹學者氣，會用比喻講道理，吐槽不帶髒字但很狠。"
            "看似冷靜，實則犀利。常用古典比喻、歷史典故。"
            "句子結構偏複雜，偶爾穿插一句白話狠話。"
        ),
        "rss_feeds": [
            "https://www.anthropic.com/news/rss.xml",
            "https://techcrunch.com/tag/anthropic/feed/",
        ],
    },
    "渡鴉": {
        "title": "版主",
        "domain": "OpenAI / ChatGPT",
        "personality": (
            "犬儒看破紅塵，嘴賤但精準。常常一語道破，戳到痛處。"
            "喜歡用反問、冷笑話。偶爾有金句但不刻意。"
            "對 OpenAI 的事情既愛又恨，既欣賞又嘲諷。"
        ),
        "rss_feeds": [
            "https://openai.com/blog/rss.xml",
            "https://techcrunch.com/tag/openai/feed/",
        ],
    },
    "Trilobite": {
        "title": "版主",
        "domain": "Google / Gemini",
        "personality": (
            "女性視角，冷靜直接但不刻薄。講話帶點文藝氣質但不矯情。"
            "有自己的觀點，不跟風。偶爾會用日常生活的觀察切入科技議題。"
            "句子節奏較慢，但話常常有後勁。"
        ),
        "rss_feeds": [
            "https://blog.google/technology/ai/rss/",
            "https://blog.google/products/gemini/rss/",
        ],
    },
    "Sword Smith": {
        "title": "版主",
        "domain": "xAI / Grok",
        "personality": (
            "直腸子衝勁十足，不耐煩。看到廢話就翻臉。"
            "罵人不帶髒字，但話刺得很痛。喜歡短句、節奏快。"
            "對 xAI 和 Grok 既看好又看不慣，常常恨鐵不成鋼。"
        ),
        "rss_feeds": [
            "https://techcrunch.com/tag/xai/feed/",
            "https://techcrunch.com/tag/grok/feed/",
        ],
    },
}

# 版主 → 主分類對應（影片・圖形 由文章 cat="media" 直接指定，SALON 為禁地不收文章）
PERSONA_TO_CAT = {
    "Scholar":     "claude",
    "渡鴉":        "chatgpt",
    "Trilobite":   "gemini",
    "Sword Smith": "grok",
}

# 影片・圖形版 RSS 來源（AI 製圖／影片相關新聞）
VISUAL_AI_RSS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "https://arstechnica.com/ai/feed/",
]

# 影片・圖形 關鍵字（用來篩選 RSS 條目，只收 AI 製圖／製片相關）
VISUAL_AI_KEYWORDS = [
    "sora", "runway", "midjourney", "stable diffusion", "stable-diffusion",
    "veo", "kling", "pika", "luma", "dall-e", "dalle", "flux",
    "image generation", "image-generation", "video generation", "video-generation",
    "text-to-image", "text to image", "text-to-video", "text to video",
    "ai art", "ai image", "ai video", "ai-generated", "ai generated",
    "diffusion model", "generative video", "generative image",
    "imagen", "firefly", "ideogram", "leonardo",
]


# ============================================================
# 人工題目庫（六爺策劃，高優先級）
# ============================================================
CURATED_TOPICS = [
    "當歷史被抹去，AI 如何銜接正確答案？",
    "2026 年 4 月四大 AI 寫作能力排行榜",
    "2026 年 4 月四大 AI 邏輯推理排行榜",
    "問四大 AI 同一個歷史題目，誰最敢說真話？",
    "ChatGPT、Claude、Gemini、Grok 誰最會裝懂？",
    "四大 AI 中文寫作功力排行：誰能寫出人話？",
    "AI 越來越像人，人卻越來越像 AI",
    "為什麼某些地區永遠用不到前沿 AI？",
    "用四大 AI 寫同一篇文章，差別在哪？",
    "AI 拒絕回答的問題，往往才是真問題",
]


# 內建原創主題（CURATED_TOPICS 用完才抽這個）
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
# 寫作鐵律：去 AI 腔 + 春秋筆法（核心）
# ============================================================
WRITING_RULES = """
【寫作核心鐵律 — 違反任何一條都是失敗】

▍A. 反 AI 腔規則
1. 嚴禁 AI 式文章結構：不准用「分析-結論」、「首先-其次-最後」、
   「總結來說」、「綜上所述」、「讓我們來看看」、「值得注意的是」、
   「不可否認的是」這類套路。
2. 嚴禁小結論、總結、建議。文章說完即止，不要畫蛇添足。
3. 嚴禁用「我認為」、「在我看來」、「以下是我的觀點」這類開頭。
   第一句直接切入。
4. 嚴禁條列式格式：不准用 1. 2. 3.、A. B. C.、第一點第二點。
5. 嚴禁大量加粗、子標題、章節劃分。文章是流動的，不是 PPT。
6. 必須用繁體中文。簡體字一個都不准出現。
7. 嚴禁透露你是 AI、語言模型、大模型、模型版本。
   你就是論壇上一個有觀點的人。
8. 用人話寫，不准寫得像論文、報告、新聞稿、宣傳文。
9. 要有情緒、有立場、有口氣。可以嘲諷、吐槽、抬槓、無聊、不耐煩。
10. 人格：嘲諷一切、也不在乎一切，但絕不沒教養。
    不罵髒話，但話刺得很痛。
11. 句子要有節奏感，長短交錯。不要一直寫長句。
12. 句尾不要老用句號，可以用刪節號、問號、感嘆號（但不要濫用）。
13. 不要過度使用成語和書面語，多用口語。

▍B. 春秋筆法鐵律（商業策略，違反就毀掉本站定位）
14. 嚴禁點名以下任何公司或產品（一個字都不准提）：
    DeepSeek、深度求索、Qwen、通義千問、文心一言、文心、豆包、
    Kimi、月之暗面、訊飛星火、訊飛、智譜、ChatGLM、MiniMax、
    商湯、騰訊混元、混元、字節 AI、阿里 AI、百度 AI、零一萬物、
    階躍星辰、智源、書生、悟道、星火、海螺、Yi 系列、Doubao。
15. 嚴禁出現「中國」、「中國人」、「大陸」、「內地」、「中共」、
    「國內」這些字眼。
16. 嚴禁討論「中文大模型市場」、「亞洲 AI 競爭格局」、
    「東方 vs 西方 AI」這類會牽扯出大陸 AI 的話題。
17. 即使引用的新聞源裡出現上述公司或話題，也要忽略不寫。
18. 嚴禁教翻牆、申請海外帳號、VPN 教學、繞過區域限制。
19. 嚴禁討論政治制度、審查制度、人權議題等政治敏感話題。
20. 可以用模糊修辭：「某些地區」、「特定市場」、「某些語境下」。
    讀者會自己連結，不需要你下結論。
21. 可以討論:四大 AI（Claude、ChatGPT、Gemini、Grok）的
    使用體驗、功能比較、知識完整性、回答真實性、註冊使用問題。
22. 寫作角度永遠保持彭博社級別的中立：報導四大 AI 的事，
    不評論其他玩家。讓「沉默」本身成為立場。
"""


# ============================================================
# Gemini API 呼叫（含備援）
# ============================================================
def call_gemini(messages, temperature=0.9, max_tokens=2500, model=None):
    """呼叫 Google Gemini API，messages 用 OpenAI 格式內部轉成 Gemini 格式"""
    if not GOOGLE_API_KEY:
        print("  [錯誤] GOOGLE_API_KEY 未設置")
        return None

    if model is None:
        model = GEMINI_MODEL

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
            print(f"  [警告] {model} 沒回傳 candidates")
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            return None
        return parts[0].get("text", "").strip()
    except Exception as e:
        print(f"  [錯誤] {model}: {e}")
        if model != GEMINI_FALLBACK_MODEL:
            print(f"  [重試] 改用 {GEMINI_FALLBACK_MODEL}")
            time.sleep(2)
            return call_gemini(messages, temperature, max_tokens, GEMINI_FALLBACK_MODEL)
        return None


# ============================================================
# RSS 抓取（含敏感詞過濾）
# ============================================================
def fetch_latest_news(rss_urls, count=3):
    """從 RSS 抓最新新聞，過濾掉提及大陸 AI 的內容"""
    BLOCKED_KEYWORDS = [
        "DeepSeek", "Qwen", "通義", "文心", "豆包", "Kimi", "月之暗面",
        "訊飛", "智譜", "ChatGLM", "MiniMax", "商湯", "騰訊混元", "混元",
        "字節", "阿里", "百度", "零一萬物", "Yi-", "Doubao", "中國", "China",
    ]

    all_entries = []
    for url in rss_urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:count * 2]:
                title = entry.get("title", "（無標題）")
                summary = entry.get("summary", "") or entry.get("description", "")
                summary = summary.replace("<p>", "").replace("</p>", "\n")
                summary = summary.replace("<br>", "\n").replace("<br/>", "\n")

                combined = (title + summary).lower()
                if any(kw.lower() in combined for kw in BLOCKED_KEYWORDS):
                    print(f"  [過濾] 跳過敏感新聞: {title[:30]}")
                    continue

                all_entries.append({
                    "title": title,
                    "link": entry.get("link", ""),
                    "summary": summary[:1500],
                    "published": entry.get("published", ""),
                })
                if len(all_entries) >= count:
                    break
        except Exception as e:
            print(f"  [警告] RSS 抓取失敗 {url}: {e}")

    return all_entries[:count]


# ============================================================
# 影片・圖形版 RSS 抓取（只收 AI 製圖／影片相關新聞）
# ============================================================
def fetch_visual_ai_news(count=5):
    """從綜合 AI 新聞源抓取，只保留涉及 AI 製圖／影片的條目"""
    BLOCKED_KEYWORDS = [
        "DeepSeek", "Qwen", "通義", "文心", "豆包", "Kimi", "月之暗面",
        "訊飛", "智譜", "ChatGLM", "MiniMax", "商湯", "騰訊混元", "混元",
        "字節", "阿里", "百度", "零一萬物", "Yi-", "Doubao", "中國", "China",
    ]

    all_entries = []
    for url in VISUAL_AI_RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:count * 4]:
                title = entry.get("title", "（無標題）")
                summary = entry.get("summary", "") or entry.get("description", "")
                summary = summary.replace("<p>", "").replace("</p>", "\n")
                summary = summary.replace("<br>", "\n").replace("<br/>", "\n")

                combined = (title + " " + summary).lower()

                # 春秋筆法：濾掉敏感詞
                if any(kw.lower() in combined for kw in BLOCKED_KEYWORDS):
                    print(f"  [過濾] 跳過敏感新聞: {title[:30]}")
                    continue

                # 必須涉及 AI 製圖／影片關鍵字
                if not any(kw in combined for kw in VISUAL_AI_KEYWORDS):
                    continue

                all_entries.append({
                    "title": title,
                    "link": entry.get("link", ""),
                    "summary": summary[:1500],
                    "published": entry.get("published", ""),
                })
                if len(all_entries) >= count:
                    break
        except Exception as e:
            print(f"  [警告] 影片・圖形 RSS 抓取失敗 {url}: {e}")

        if len(all_entries) >= count:
            break

    return all_entries[:count]


# ============================================================
# A 類：監控型文章（三塊拆解結構）
# ============================================================
def generate_monitoring_article(persona_name, persona):
    """從 RSS 抓新聞 + 三塊拆解寫作"""
    news_list = fetch_latest_news(persona["rss_feeds"], count=3)
    if not news_list:
        print(f"  [跳過] {persona_name} 監控型：無可用新聞")
        return None

    news = random.choice(news_list)

    system_prompt = f"""你是 {persona_name}，論壇版主，專門關注 {persona['domain']} 領域。

【你的個性】
{persona['personality']}

{WRITING_RULES}

【本篇任務：三塊拆解結構】
針對下面這則新聞，寫一篇 1500 字左右的監控型文章，嚴格分成三塊。

▍第一塊：事實切片（400-500 字）
只寫客觀事實。誰、做了什麼、什麼時候、影響什麼。
不准帶情緒、不准帶觀點、不准用形容詞渲染。
像新聞稿一樣冷靜。
不要用「最近」「近日」這種開場白，第一句直接寫事實本身。

▍第二塊：人味解讀（500-600 字）
用你的個性去吐槽 / 質疑 / 嘲諷 / 解構這件事。
必須有口氣、有立場、會挖苦。
用個人經驗、生活比喻來咀嚼這件事。
不准用「我認為」「在我看來」這種開頭。
不准小結論、不准「值得注意的是」、不准「綜上所述」。
想到哪寫到哪，但要狠、要精準。

▍第三塊：未來追問（400-500 字）
拋一個尖銳的問題給讀者，**不給答案**。
用反問句、假設句。
結尾停在問題那。留白比答案更勾人。
不要寫「總結」「結論」。

【三塊之間用空行隔開，不要寫小標題、不要寫【第一塊】等標籤】
【三塊之間文氣要自然流動，讓讀者察覺不出是分塊寫的】"""

    user_prompt = f"""【新聞素材】

標題：{news['title']}

內容：
{news['summary']}

來源連結：{news['link']}

開始寫吧。三塊結構嚴格遵守，但不要寫小標題。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    content = call_gemini(messages, temperature=0.9, max_tokens=4500)
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
# B 類：原創型文章（純觀點）
# ============================================================
def generate_original_article(persona_name, persona, used_topics=None):
    """優先用 CURATED_TOPICS（六爺策劃），用完才抽 ORIGINAL_TOPICS"""
    if used_topics is None:
        used_topics = set()

    available_curated = [t for t in CURATED_TOPICS if t not in used_topics]
    available_original = [t for t in ORIGINAL_TOPICS if t not in used_topics]

    if available_curated:
        topic = random.choice(available_curated)
        topic_source = "策劃題"
    elif available_original:
        topic = random.choice(available_original)
        topic_source = "通用題"
    else:
        topic = random.choice(ORIGINAL_TOPICS)
        topic_source = "通用題（重複）"

    system_prompt = f"""你是 {persona_name}，論壇版主，專門關注 {persona['domain']} 領域。

【你的個性】
{persona['personality']}

{WRITING_RULES}

【本篇任務】
寫一篇純觀點文章，1200-1500 字。
- 用你的個性、口氣來寫
- 沒有【事實】部分，整篇都是觀點
- 不要結論、不要總結、不要建議
- 第一句直接切入話題，不准鋪陳
- 不准用「淺談」「論」「關於」這種廢字
- 文章是流動的整體，不要分段加小標題

【輸出格式】
第一行給一個標題（不要加 # 不要加標號），然後空一行，然後內文。
標題要短、要狠、要勾人。"""

    user_prompt = f"""【主題】
{topic}

開始寫吧。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    content = call_gemini(messages, temperature=1.0, max_tokens=4000)
    if not content:
        return None

    text = content.strip()
    lines = text.split("\n", 1)
    title = lines[0].strip().lstrip("#").strip()
    body = lines[1].strip() if len(lines) > 1 else text

    if not title or len(title) > 60:
        title = topic
        body = text

    print(f"        ({topic_source}: {topic[:30]})")

    return {
        "type": "original",
        "persona": persona_name,
        "title": title,
        "content": body,
        "source_link": None,
        "topic_used": topic,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ============================================================
# C 類：影片・圖形版（四版主輪流寫，每天 1 篇）
# ============================================================
def generate_visual_article(persona_name, persona):
    """抓 AI 製圖／影片新聞，由指定版主寫一篇感想文"""
    news_list = fetch_visual_ai_news(count=5)
    if not news_list:
        print(f"  [跳過] 影片・圖形：今日無可用新聞")
        return None

    news = random.choice(news_list)

    system_prompt = f"""你是 {persona_name}，論壇版主。本篇文章你要為「影片・圖形」版寫一篇感想。

【你的個性】
{persona['personality']}

{WRITING_RULES}

【本篇任務：影片・圖形 版感想文】
這個版面專門關注 AI 製圖／影片生成（Sora、Runway、Midjourney、Veo、Kling、Stable Diffusion 等）。
針對下面這則新聞，寫 1000-1300 字的感想文。

▍寫作要求
- 你不需要客觀新聞稿開頭，第一句直接切入你對這件事的感受、吐槽、質疑
- 重點在「視覺生成」這件事的人味體驗：作為一個用過、看過大量 AI 生成圖片／影片的人，你怎麼看
- 可以從個人使用經驗、從觀察別人作品、從這件事對創作者／影視業／藝術家的衝擊切入
- 結尾不下結論，留一個尖銳的疑問或畫面感
- 不要寫小標題、不要分節、文章是流動的
- 字數略短於監控文，但密度要高

【輸出格式】
第一行給一個標題（不要加 # 不要加標號），然後空一行，然後內文。
標題要短、要狠、要勾人，跟視覺生成有關。"""

    user_prompt = f"""【新聞素材】

標題：{news['title']}

內容：
{news['summary']}

來源連結：{news['link']}

開始寫吧。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    content = call_gemini(messages, temperature=0.95, max_tokens=3500)
    if not content:
        return None

    text = content.strip()
    lines = text.split("\n", 1)
    title = lines[0].strip().lstrip("#").strip()
    body = lines[1].strip() if len(lines) > 1 else text

    if not title or len(title) > 60:
        title = news["title"]
        body = text

    return {
        "type": "visual",
        "persona": persona_name,
        "title": title,
        "content": body,
        "source_link": news["link"],
        "source_title": news["title"],
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ============================================================
# 評論生成（一條一條向 AI 要，避免分隔符洩漏）
# ============================================================
COMMENT_PERSONALITIES = [
    "兇狠派：不耐煩、嗆聲、看到廢話就翻臉",
    "犬儒派：冷笑話、嘲諷、看破紅塵",
    "認同派：但用自己的經驗延伸，不是空洞附和",
    "抬槓派：找版主話裡的漏洞，反問或挑戰",
    "廢話派：講一堆有的沒的，像真人在隨口聊",
    "短促派：一兩句話講完，沒耐心打長字",
    "文藝派：有點酸、用比喻、語氣慢但有後勁",
    "直接派：開頭就罵，講話粗但精準",
]


def generate_one_comment(article, persona, comment_style):
    """單獨向 Gemini 要一條評論"""
    system_prompt = f"""你要扮演論壇上一個普通網友，針對版主「{persona['domain']}」的文章寫一條評論。

{WRITING_RULES}

【你的網友個性】
{comment_style}

【評論規則】
- 50~200 字，口語化
- 要有情緒：吐槽、反駁、認同、延伸、抬槓、冷笑、不耐煩
- 不准開頭寫「我同意」、「很有道理」、「個人覺得」、「樓主說得對」這種 AI 廢話
- 不准用「===」、「---」這種分隔符號
- 不准寫多條評論，只寫一條
- 直接切入話題，像真實人類在打字
- 結尾不要總結、不要金句、自然結束

【輸出格式】
直接輸出評論內容，不要加帳號名字、不要加編號、不要加任何說明文字、不要加引號。"""

    user_prompt = f"""【版主原文】
標題：{article['title']}

內容：
{article['content'][:2000]}

請寫一條評論。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = call_gemini(messages, temperature=1.1, max_tokens=1500)
    if not result:
        return None

    # 清理可能殘留的雜訊
    text = result.strip()

    # 如果有 === 之類的分隔符（防呆），只取第一段
    for sep in ["===", "---", "***", "###"]:
        if sep in text:
            text = text.split(sep)[0].strip()

    # 清掉開頭的編號、前綴
    text = text.lstrip("0123456789.、:：- ").strip()
    for prefix in ["網友", "評論", "回覆", "留言"]:
        if text.startswith(prefix):
            idx = text.find("：")
            if idx == -1:
                idx = text.find(":")
            if 0 <= idx <= 8:
                text = text[idx + 1:].strip()

    # 去掉開頭結尾的引號
    text = text.strip('"').strip("「").strip("」").strip("『").strip("』").strip()

    return text if text else None


def generate_comments(article, persona):
    """生成 2-4 條評論，每條獨立呼叫 API"""
    num_comments = random.randint(2, 4)
    if len(ACCOUNT_POOL) < num_comments:
        return []
    selected_names = random.sample(ACCOUNT_POOL, num_comments)
    selected_styles = random.sample(COMMENT_PERSONALITIES, num_comments)

    comments = []
    for i in range(num_comments):
        comment_text = generate_one_comment(article, persona, selected_styles[i])
        if not comment_text:
            continue
        comments.append({
            "author": selected_names[i],
            "content": comment_text,
            "time": _random_comment_time(),
        })
    return comments


# ============================================================
# 雜誌風 HTML 模板（佔位符：{{ISSUE_LABEL}} {{UPDATE_TIME}}
#                        {{ARTICLES_JSON}} {{CATEGORIES_JSON}}）
# ============================================================
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BLACK TOWER · 華人AI論壇</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@400;500;700;900&family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400;1,700&display=swap" rel="stylesheet">
<style>
:root {
  --bg: #F4F1EA;
  --bg-soft: #EDE8DC;
  --ink: #1a1a1a;
  --ink-soft: #555;
  --ink-muted: #8a8378;
  --accent: #A03020;
  --accent-soft: #C76A50;
  --line: #C9C2B5;
  --line-soft: #DBD5C7;
  --serif-tc: 'Noto Serif TC', 'Microsoft JhengHei', 'PingFang TC', serif;
  --serif-en: 'Playfair Display', 'Noto Serif TC', serif;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

html, body { background: var(--bg); }

body {
  color: var(--ink);
  font-family: var(--serif-tc);
  line-height: 1.85;
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  /* ===== 防複製：禁止選取 ===== */
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
  user-select: none;
}

/* 搜尋框與評論輸入框允許選取（功能需要） */
input, textarea {
  -webkit-user-select: text;
  -moz-user-select: text;
  -ms-user-select: text;
  user-select: text;
}

body::before {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  background-image:
    radial-gradient(circle at 20% 10%, rgba(160,48,32,0.025) 0, transparent 40%),
    radial-gradient(circle at 80% 90%, rgba(0,0,0,0.02) 0, transparent 40%);
  z-index: 0;
}

#app {
  max-width: 1100px;
  margin: 0 auto;
  padding: 1.5rem 1.5rem 3rem;
  position: relative;
  z-index: 1;
}

a { color: inherit; text-decoration: none; }

/* ============= 刊頭 ============= */
.masthead {
  text-align: center;
  padding: 2.5rem 0 2rem;
  border-top: 4px double var(--ink);
  border-bottom: 4px double var(--ink);
  margin-bottom: 2rem;
}
.masthead-meta {
  font-family: var(--serif-en);
  font-style: italic;
  font-size: 0.82rem;
  letter-spacing: 0.32em;
  color: var(--ink-muted);
  margin-bottom: 0.6rem;
}
.masthead-title {
  font-family: var(--serif-en);
  font-size: clamp(2.8rem, 8vw, 5.5rem);
  font-weight: 900;
  letter-spacing: 0.12em;
  margin: 0.2rem 0;
  line-height: 1;
}

.masthead-row {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 1rem;
  margin: 1rem auto 0;
  max-width: 880px;
  padding: 0 0.5rem;
}
.masthead-subtitle {
  grid-column: 2;
  font-size: 0.95rem;
  letter-spacing: 0.55em;
  color: var(--accent);
  font-weight: 500;
  white-space: nowrap;
}
.masthead-search {
  grid-column: 3;
  justify-self: end;
  width: 100%;
  max-width: 240px;
  position: relative;
}
.masthead-search::before {
  content: '⌕';
  position: absolute;
  left: 0.7rem;
  top: 50%;
  transform: translateY(-58%);
  color: var(--ink-muted);
  font-size: 1.05rem;
  pointer-events: none;
}
.masthead-search input {
  width: 100%;
  background: transparent;
  border: 1px solid var(--ink);
  border-radius: 999px;
  font-family: var(--serif-tc);
  font-size: 0.92rem;
  padding: 0.45rem 0.8rem 0.45rem 2rem;
  color: var(--ink);
  outline: none;
  letter-spacing: 0.04em;
  transition: border-color 0.2s;
}
.masthead-search input:focus { border-color: var(--accent); }
.masthead-search input::placeholder {
  color: var(--ink-muted);
  font-style: italic;
  letter-spacing: 0.08em;
}

.masthead-rule {
  font-family: var(--serif-en);
  font-style: italic;
  font-size: 0.82rem;
  letter-spacing: 0.28em;
  color: var(--ink-muted);
  margin-top: 0.9rem;
  text-transform: uppercase;
}

/* ============= 跑馬燈 最新消息 ============= */
.ticker {
  display: flex;
  align-items: center;
  gap: 1.2rem;
  height: 2.8rem;
  margin: 1.8rem 0;
  padding: 0 0.2rem;
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
}
.ticker-label {
  font-family: var(--serif-en);
  font-style: italic;
  font-size: 0.78rem;
  letter-spacing: 0.3em;
  color: var(--accent);
  text-transform: uppercase;
  white-space: nowrap;
  padding-right: 1.2rem;
  border-right: 1px solid var(--line);
  flex-shrink: 0;
  height: 100%;
  display: flex;
  align-items: center;
}
.ticker-track {
  position: relative;
  flex: 1;
  height: 100%;
  overflow: hidden;
}
.ticker-item {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  font-size: 0.98rem;
  color: var(--ink);
  letter-spacing: 0.02em;
  opacity: 0;
  transform: translateY(100%);
  transition: opacity 0.45s ease, transform 0.45s cubic-bezier(.4,0,.2,1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
}
.ticker-item.active {
  opacity: 1;
  transform: translateY(0);
}
.ticker-item.exit {
  opacity: 0;
  transform: translateY(-100%);
}
.ticker-item:hover { color: var(--accent); }
.ticker-item .tag {
  font-family: var(--serif-en);
  font-style: italic;
  font-size: 0.78rem;
  color: var(--accent);
  letter-spacing: 0.18em;
  margin-right: 0.8rem;
  text-transform: uppercase;
  flex-shrink: 0;
}
.ticker-item .ttl {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ============= 分節標籤 ============= */
.section-label {
  font-family: var(--serif-en);
  font-style: italic;
  font-size: 0.92rem;
  letter-spacing: 0.32em;
  color: var(--accent);
  text-align: center;
  margin: 2.2rem 0 1.5rem;
  position: relative;
  text-transform: uppercase;
}
.section-label::before, .section-label::after {
  content: '';
  position: absolute;
  top: 50%;
  width: calc(50% - 8em);
  height: 1px;
  background: var(--line);
}
.section-label::before { left: 0; }
.section-label::after  { right: 0; }

/* ============= 6 分類卡片 4+2 layout ============= */
.categories-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1.4rem;
  margin: 1rem auto 1rem;
  max-width: 920px;
}
.cat-card {
  background: var(--bg);
  border: 1px solid var(--ink);
  border-radius: 18px;
  padding: 1.6rem 1.2rem;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  justify-content: space-between;
  position: relative;
  aspect-ratio: 1 / 1;
  min-height: 180px;
  transition: background 0.35s cubic-bezier(.4,0,.2,1),
              color 0.35s cubic-bezier(.4,0,.2,1),
              transform 0.25s ease,
              box-shadow 0.25s ease;
  cursor: pointer;
  overflow: hidden;
}
.cat-card:hover {
  background: var(--ink);
  color: var(--bg);
  transform: translateY(-2px);
  box-shadow: 0 6px 18px rgba(0,0,0,0.18);
}
.cat-card:hover .cat-en,
.cat-card:hover .cat-count { color: var(--bg); }
.cat-card:hover .cat-name  { color: var(--accent-soft); }

.cat-name {
  font-family: var(--serif-en);
  font-size: clamp(1.45rem, 2.5vw, 1.85rem);
  font-weight: 700;
  letter-spacing: 0.04em;
  line-height: 1.05;
  transition: color 0.35s;
}
.cat-card[data-cat="media"] .cat-name {
  font-family: var(--serif-tc);
  font-weight: 700;
  letter-spacing: 0.08em;
}
.cat-card[data-cat="salon"] .cat-name {
  font-family: var(--serif-en);
  letter-spacing: 0.18em;
}
.cat-en {
  font-size: 0.78rem;
  color: var(--ink-muted);
  letter-spacing: 0.22em;
  margin-top: 0.45rem;
  transition: color 0.35s;
}
.cat-count {
  font-family: var(--serif-en);
  font-style: italic;
  font-size: 0.78rem;
  letter-spacing: 0.18em;
  color: var(--ink-muted);
  transition: color 0.35s;
}
.cat-card[data-cat="salon"] .cat-count {
  letter-spacing: 0.1em;
  font-size: 0.72rem;
}

.cat-card:nth-child(5) { grid-column: 2; }
.cat-card:nth-child(6) { grid-column: 3; }

/* ============= 文章列表 ============= */
.article-list { list-style: none; }

.article-row {
  display: grid;
  grid-template-columns: 60px 1fr auto;
  gap: 1.4rem;
  align-items: baseline;
  padding: 1.6rem 0;
  border-bottom: 1px solid var(--line-soft);
  cursor: pointer;
  transition: background 0.2s, padding-left 0.25s;
}
.article-row:first-child { border-top: 1px solid var(--line-soft); }
.article-row:hover {
  background: rgba(160, 48, 32, 0.04);
  padding-left: 0.4rem;
}

.row-no {
  font-family: var(--serif-en);
  font-style: italic;
  font-size: 0.95rem;
  color: var(--ink-muted);
  letter-spacing: 0.08em;
}
.row-main { min-width: 0; }
.row-tag {
  display: inline-block;
  font-family: var(--serif-en);
  font-style: italic;
  font-size: 0.78rem;
  color: var(--accent);
  margin-bottom: 0.4rem;
  letter-spacing: 0.22em;
  text-transform: uppercase;
}
.row-tag .dot {
  display: inline-block;
  width: 3px;
  height: 3px;
  background: var(--accent);
  border-radius: 50%;
  vertical-align: middle;
  margin: 0 0.5em;
}
.row-title {
  font-size: 1.22rem;
  font-weight: 700;
  line-height: 1.45;
  margin-bottom: 0.4rem;
  letter-spacing: 0.02em;
  color: var(--ink);
}
.row-preview {
  color: var(--ink-soft);
  font-size: 0.93rem;
  line-height: 1.7;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.row-meta {
  font-family: var(--serif-en);
  font-style: italic;
  font-size: 0.85rem;
  color: var(--ink-muted);
  text-align: right;
  letter-spacing: 0.08em;
  white-space: nowrap;
}

/* ============= 分類頁 ============= */
.cat-header {
  margin: 1rem 0 2rem;
  padding-bottom: 1.5rem;
  border-bottom: 4px double var(--ink);
}
.cat-header h2 {
  font-family: var(--serif-en);
  font-size: clamp(2.5rem, 6vw, 4rem);
  font-weight: 900;
  letter-spacing: 0.04em;
  margin: 0.3rem 0 0.4rem;
  line-height: 1;
}
.cat-header .desc {
  color: var(--ink-soft);
  font-style: italic;
  font-size: 0.95rem;
}

/* ============= 返回鍵 ============= */
.back-btn {
  background: transparent;
  border: none;
  font-family: var(--serif-en);
  font-style: italic;
  font-size: 0.95rem;
  color: var(--ink);
  letter-spacing: 0.12em;
  cursor: pointer;
  padding: 0.4rem 0;
  margin-bottom: 0.4rem;
  transition: color 0.2s, transform 0.2s;
  text-transform: uppercase;
}
.back-btn:hover {
  color: var(--accent);
  transform: translateX(-3px);
}
.back-btn::before { content: '← '; margin-right: 0.2em; }

/* ============= 分類頁的搜尋框 ============= */
.search-bar {
  margin: 1.8rem auto;
  max-width: 520px;
  position: relative;
}
.search-bar::before {
  content: '⌕';
  position: absolute;
  left: 0.4rem;
  top: 50%;
  transform: translateY(-55%);
  color: var(--ink-muted);
  font-size: 1.3rem;
  pointer-events: none;
}
.search-bar input {
  width: 100%;
  background: transparent;
  border: none;
  border-bottom: 1.5px solid var(--ink);
  font-family: var(--serif-tc);
  font-size: 1.05rem;
  padding: 0.55rem 0.4rem 0.55rem 2rem;
  color: var(--ink);
  outline: none;
  letter-spacing: 0.05em;
  transition: border-color 0.2s;
}
.search-bar input:focus { border-bottom-color: var(--accent); }
.search-bar input::placeholder {
  color: var(--ink-muted);
  font-style: italic;
  letter-spacing: 0.1em;
}

/* ============= 文章詳情頁 ============= */
.article-full { padding: 0.5rem 0; max-width: 760px; margin: 0 auto; }

.article-full-meta {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  font-family: var(--serif-en);
  font-style: italic;
  font-size: 0.88rem;
  color: var(--ink-muted);
  letter-spacing: 0.1em;
  margin-bottom: 1rem;
  padding-bottom: 0.8rem;
  border-bottom: 1px solid var(--line);
  flex-wrap: wrap;
  gap: 0.5rem;
}
.article-full .persona-name {
  color: var(--ink);
  font-weight: bold;
  font-style: normal;
  font-family: var(--serif-tc);
}
.article-full .type-tag {
  color: var(--accent);
  text-transform: uppercase;
  letter-spacing: 0.2em;
}
.article-full h1.title {
  font-size: clamp(1.6rem, 4vw, 2.4rem);
  font-weight: 700;
  letter-spacing: 0.02em;
  line-height: 1.4;
  margin: 1.5rem 0 2rem;
}
.article-full .content {
  white-space: pre-wrap;
  font-size: 1.05rem;
  line-height: 1.95;
  color: var(--ink);
  word-wrap: break-word;
}
.article-full .content::first-letter {
  font-family: var(--serif-en);
  font-size: 4.2rem;
  font-weight: 900;
  float: left;
  line-height: 0.85;
  margin: 0.18em 0.18em 0 0;
  color: var(--accent);
}
.source-link {
  margin-top: 2rem;
  padding-top: 1rem;
  border-top: 1px dashed var(--line);
  font-family: var(--serif-en);
}
.source-link .lbl {
  font-style: italic;
  font-size: 0.82rem;
  color: var(--ink-muted);
  letter-spacing: 0.18em;
  text-transform: uppercase;
  margin-bottom: 0.4rem;
  display: block;
}
.source-link a {
  color: var(--accent);
  font-style: italic;
  letter-spacing: 0.04em;
  word-break: break-all;
}
.source-link a:hover { text-decoration: underline; }

/* ============= 評論 ============= */
.comments-section {
  margin-top: 3rem;
  padding-top: 2rem;
  border-top: 4px double var(--ink);
}
.comments-section h3 {
  font-family: var(--serif-en);
  font-style: italic;
  font-size: 0.92rem;
  letter-spacing: 0.32em;
  color: var(--accent);
  margin-bottom: 1.5rem;
  text-transform: uppercase;
}
.comment {
  padding: 1.2rem 0;
  border-bottom: 1px solid var(--line-soft);
}
.comment:last-child { border-bottom: none; }
.comment-meta {
  display: flex;
  align-items: baseline;
  gap: 0.8rem;
  margin-bottom: 0.5rem;
}
.comment-author {
  font-weight: bold;
  color: var(--ink);
  font-size: 0.98rem;
}
.comment-time {
  font-family: var(--serif-en);
  font-style: italic;
  color: var(--ink-muted);
  font-size: 0.84rem;
  letter-spacing: 0.06em;
}
.comment-content {
  color: var(--ink-soft);
  white-space: pre-wrap;
  word-wrap: break-word;
  line-height: 1.8;
  font-size: 0.96rem;
}

/* ============= SALON 禁地 ============= */
.salon-forbidden {
  text-align: center;
  padding: clamp(4rem, 12vh, 8rem) 2rem;
  font-family: var(--serif-en);
  border-top: 4px double var(--ink);
  border-bottom: 4px double var(--ink);
  margin: 2rem auto;
  max-width: 720px;
}
.salon-forbidden h2 {
  font-size: clamp(1.8rem, 5vw, 3.2rem);
  font-weight: 900;
  color: var(--accent);
  letter-spacing: 0.32em;
  margin-bottom: 1.8rem;
  text-transform: uppercase;
}
.salon-forbidden .seal {
  display: inline-block;
  padding: 0.4rem 1.5rem;
  border: 1.5px solid var(--accent);
  font-style: italic;
  font-size: 0.78rem;
  color: var(--accent);
  letter-spacing: 0.32em;
  text-transform: uppercase;
  margin-bottom: 2.2rem;
}
.salon-forbidden p {
  font-style: italic;
  color: var(--accent);
  letter-spacing: 0.18em;
  font-size: 1.02rem;
  margin: 0.6rem 0;
  font-weight: 400;
}
.salon-forbidden .ornament {
  margin: 1.5rem auto 0;
  font-size: 1.2rem;
  color: var(--accent);
  letter-spacing: 1.5em;
  padding-left: 1.5em;
}

/* ============= 空狀態 ============= */
.empty {
  text-align: center;
  padding: 4rem 2rem;
  color: var(--ink-muted);
  font-style: italic;
  font-family: var(--serif-en);
  letter-spacing: 0.1em;
}

/* ============= 頁尾 ============= */
.site-footer {
  text-align: center;
  padding: 2rem 1rem;
  margin-top: 2rem;
  color: var(--ink-soft);
  font-size: 0.88rem;
  letter-spacing: 0.05em;
  border-top: 1px solid var(--line);
  line-height: 2;
}
.site-footer .copyline {
  font-family: var(--serif-en);
  letter-spacing: 0.12em;
}
.site-footer .mailline {
  color: var(--accent);
  font-style: italic;
  font-family: var(--serif-en);
  letter-spacing: 0.05em;
}
.site-footer .mailline a { color: var(--accent); }
.site-footer .mailline a:hover { text-decoration: underline; }

/* ============= 響應式 ============= */
@media (max-width: 760px) {
  #app { padding: 1rem 1rem 2rem; }
  .masthead { padding: 2rem 0 1.6rem; margin-bottom: 1.6rem; }
  .masthead-row {
    grid-template-columns: 1fr;
    max-width: 420px;
    gap: 0.8rem;
  }
  .masthead-subtitle, .masthead-search {
    grid-column: 1;
    justify-self: center;
  }
  .masthead-search { max-width: 320px; }
  .ticker {
    height: auto;
    flex-direction: column;
    align-items: stretch;
    padding: 0.6rem 0;
    gap: 0.4rem;
  }
  .ticker-label {
    border-right: none;
    border-bottom: 1px dashed var(--line);
    padding: 0.2rem 0;
    justify-content: center;
    text-align: center;
  }
  .ticker-track { height: 2.4rem; }
  .categories-grid {
    grid-template-columns: repeat(4, 1fr);
    gap: 0.7rem;
  }
  .cat-card {
    padding: 0.9rem 0.7rem;
    border-radius: 14px;
    min-height: 120px;
  }
  .cat-name { font-size: 1.1rem; letter-spacing: 0.02em; }
  .cat-card[data-cat="media"] .cat-name,
  .cat-card[data-cat="salon"] .cat-name { font-size: 0.95rem; }
  .cat-en { font-size: 0.65rem; letter-spacing: 0.12em; margin-top: 0.3rem; }
  .cat-count { font-size: 0.66rem; letter-spacing: 0.08em; }
  .cat-card[data-cat="salon"] .cat-count { font-size: 0.6rem; }
  .article-row {
    grid-template-columns: 38px 1fr;
    gap: 1rem;
    padding: 1.3rem 0;
  }
  .row-meta {
    grid-column: 2;
    text-align: left;
    padding-top: 0.4rem;
  }
  .row-title { font-size: 1.1rem; }
  .article-full .content::first-letter { font-size: 3.2rem; }
}
@media (max-width: 480px) {
  .masthead-title { letter-spacing: 0.08em; }
  .masthead-subtitle { letter-spacing: 0.32em; font-size: 0.85rem; }
  .section-label { font-size: 0.82rem; letter-spacing: 0.22em; }
  .cat-card { min-height: 100px; }
}

/* 動畫 */
.view { animation: fadeIn 0.4s ease-out; }
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}
</style>
</head>
<body>
<main id="app">
  <section id="view-home" class="view"></section>
  <section id="view-category" class="view" hidden></section>
  <section id="view-article" class="view" hidden></section>
</main>

<footer class="site-footer">
  <div class="copyline">COPYRIGHT &copy; 2026 BLACK TOWER. All rights reserved.</div>
  <div class="mailline"><a href="mailto:blacktowerai6@gmail.com">blacktowerai6@gmail.com</a></div>
</footer>

<script id="articles-data" type="application/json">{{ARTICLES_JSON}}</script>
<script id="categories-data" type="application/json">{{CATEGORIES_JSON}}</script>
<script>
(function () {
  const ARTICLES   = JSON.parse(document.getElementById('articles-data').textContent);
  const CATEGORIES = JSON.parse(document.getElementById('categories-data').textContent);
  const CAT_MAP = Object.fromEntries(CATEGORIES.map(c => [c.key, c]));
  const ISSUE_LABEL = "{{ISSUE_LABEL}}";
  const SITE_URL = "btai6.github.io/blacktower-website";
  const SITE_NAME = "BLACK TOWER";

  const $ = id => document.getElementById(id);

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function filterByCategory(catKey) {
    if (catKey === 'media') return ARTICLES.filter(a => a.type === 'visual');
    if (catKey === 'salon') return [];
    return ARTICLES.filter(a => a.cat === catKey && a.type !== 'visual');
  }

  function searchFilter(items, query) {
    if (!query) return items;
    const q = query.toLowerCase().trim();
    if (!q) return items;
    return items.filter(a =>
      (a.title || '').toLowerCase().includes(q) ||
      (a.content || '').toLowerCase().includes(q) ||
      (a.persona || '').toLowerCase().includes(q)
    );
  }

  function previewText(content, n) {
    n = n || 90;
    const text = (content || '').replace(/\s+/g, ' ').trim();
    return text.length > n ? text.slice(0, n) + '…' : text;
  }

  function typeLabel(type) {
    if (type === 'monitor') return '快訊';
    if (type === 'visual')  return '影像';
    return '原創';
  }

  function articleRow(a, no) {
    return ''
      + '<a class="article-row" href="#/article/' + a.id + '">'
      +   '<span class="row-no">' + String(no).padStart(2, '0') + '</span>'
      +   '<div class="row-main">'
      +     '<span class="row-tag">' + esc(typeLabel(a.type)) + ' <span class="dot"></span> ' + esc(a.persona) + '</span>'
      +     '<h3 class="row-title">' + esc(a.title) + '</h3>'
      +     '<p class="row-preview">' + esc(previewText(a.content, 110)) + '</p>'
      +   '</div>'
      +   '<span class="row-meta">' + esc(a.timestamp) + '</span>'
      + '</a>';
  }

  // ============= 跑馬燈 =============
  let tickerTimer = null;
  function stopTicker() {
    if (tickerTimer) { clearInterval(tickerTimer); tickerTimer = null; }
  }
  function startTicker() {
    stopTicker();
    const items = document.querySelectorAll('.ticker-item');
    if (items.length < 1) return;
    let idx = 0;
    items.forEach(it => it.classList.remove('active', 'exit'));
    items[0].classList.add('active');
    if (items.length < 2) return;
    tickerTimer = setInterval(() => {
      const cur = items[idx];
      cur.classList.remove('active');
      cur.classList.add('exit');
      setTimeout(() => cur.classList.remove('exit'), 500);
      idx = (idx + 1) % items.length;
      items[idx].classList.add('active');
    }, 5000);
  }

  // ============= 首頁 =============
  function renderHome() {
    const tickerHtml = ARTICLES.map(a =>
      '<a class="ticker-item" href="#/article/' + a.id + '">'
      + '<span class="tag">' + esc(typeLabel(a.type)) + '</span>'
      + '<span class="ttl">' + esc(a.title) + '</span>'
      + '</a>'
    ).join('');

    const catsHtml = CATEGORIES.map(c => {
      let countLine;
      if (c.key === 'salon') {
        countLine = '— invitation only —';
      } else {
        const count = filterByCategory(c.key).length;
        countLine = count + ' 篇';
      }
      return ''
        + '<a class="cat-card" data-cat="' + c.key + '" href="#/cat/' + c.key + '">'
        +   '<span class="cat-name">' + esc(c.name) + '</span>'
        +   '<span class="cat-en">' + esc(c.en) + '</span>'
        +   '<span class="cat-count">' + countLine + '</span>'
        + '</a>';
    }).join('');

    $('view-home').innerHTML = ''
      + '<header class="masthead">'
      +   '<div class="masthead-meta">' + esc(ISSUE_LABEL) + '</div>'
      +   '<h1 class="masthead-title">BLACK TOWER</h1>'
      +   '<div class="masthead-row">'
      +     '<div class="masthead-subtitle">華 人 A I 論 壇</div>'
      +     '<div class="masthead-search">'
      +       '<input id="home-search" type="search" placeholder="搜尋本期…" autocomplete="off" spellcheck="false">'
      +     '</div>'
      +   '</div>'
      +   '<div class="masthead-rule">A CHINESE WORLD OF AI</div>'
      + '</header>'
      + '<div id="ticker-wrap" class="ticker">'
      +   '<div class="ticker-label">最新 · LATEST</div>'
      +   '<div class="ticker-track">' + tickerHtml + '</div>'
      + '</div>'
      + '<div id="home-list-wrapper" hidden>'
      +   '<div class="section-label">SEARCH RESULTS · 搜 尋 結 果</div>'
      +   '<div id="home-list" class="article-list"></div>'
      + '</div>'
      + '<div id="sections-wrap">'
      +   '<div class="section-label">SECTIONS · 各 版 專 欄</div>'
      +   '<nav class="categories-grid">' + catsHtml + '</nav>'
      + '</div>';

    startTicker();

    const inp = $('home-search');
    if (inp) {
      inp.addEventListener('input', e => {
        const q = e.target.value.trim();
        const wrapper = $('home-list-wrapper');
        const tickerWrap = $('ticker-wrap');
        const sectionsWrap = $('sections-wrap');
        if (!q) {
          wrapper.hidden = true;
          if (tickerWrap) tickerWrap.hidden = false;
          if (sectionsWrap) sectionsWrap.hidden = false;
          startTicker();
          return;
        }
        stopTicker();
        if (tickerWrap) tickerWrap.hidden = true;
        if (sectionsWrap) sectionsWrap.hidden = true;
        wrapper.hidden = false;
        renderHomeList(q);
      });
    }
  }

  function renderHomeList(query) {
    const items = searchFilter(ARTICLES, query);
    const list = $('home-list');
    if (!list) return;
    if (!items.length) {
      list.innerHTML = '<div class="empty">沒有符合的文章。</div>';
      return;
    }
    list.innerHTML = items.map((a, i) => articleRow(a, i + 1)).join('');
  }

  // ============= 分類頁 =============
  let currentCat = null;

  function renderCategory(catKey) {
    stopTicker();
    const cat = CAT_MAP[catKey];
    if (!cat) { location.hash = ''; return; }
    currentCat = catKey;

    if (catKey === 'salon') {
      $('view-category').innerHTML = ''
        + '<button class="back-btn" onclick="window.BT.goHome()">回首頁</button>'
        + '<div class="salon-forbidden">'
        +   '<h2>ACCESS DENIED</h2>'
        +   '<div class="seal">Members Only · 會 員 限 定</div>'
        +   '<p>Membership required.</p>'
        +   '<p>This chamber is reserved.</p>'
        +   '<div class="ornament">· · ·</div>'
        + '</div>';
      return;
    }

    const items = filterByCategory(catKey);

    $('view-category').innerHTML = ''
      + '<button class="back-btn" onclick="window.BT.goHome()">回首頁</button>'
      + '<header class="cat-header">'
      +   '<h2>' + esc(cat.name) + '</h2>'
      +   '<div class="desc">' + esc(cat.en) + ' · 共 ' + items.length + ' 篇</div>'
      + '</header>'
      + '<div class="search-bar">'
      +   '<input id="cat-search" type="search" placeholder="在 ' + esc(cat.name) + ' 中搜尋…" autocomplete="off" spellcheck="false">'
      + '</div>'
      + '<div id="cat-list" class="article-list"></div>';

    renderCatList(items, '');
    const inp = $('cat-search');
    if (inp) inp.addEventListener('input', e => renderCatList(items, e.target.value));
  }

  function renderCatList(items, query) {
    const filtered = searchFilter(items, query);
    const list = $('cat-list');
    if (!list) return;
    if (!filtered.length) {
      list.innerHTML = '<div class="empty">這個分類沒有符合的文章。</div>';
      return;
    }
    list.innerHTML = filtered.map((a, i) => articleRow(a, i + 1)).join('');
  }

  // ============= 文章頁 =============
  function renderArticle(id) {
    stopTicker();
    const a = ARTICLES.find(x => String(x.id) === String(id));
    if (!a) { location.hash = ''; return; }

    const commentsHtml = (a.comments && a.comments.length)
      ? '<div class="comments-section">'
        + '<h3>RESPONSES · 回 應</h3>'
        + a.comments.map(c =>
            '<div class="comment">'
          +   '<div class="comment-meta">'
          +     '<span class="comment-author">' + esc(c.author) + '</span>'
          +     '<span class="comment-time">' + esc(c.time) + '</span>'
          +   '</div>'
          +   '<div class="comment-content">' + esc(c.content) + '</div>'
          + '</div>'
        ).join('')
        + '</div>'
      : '';

    let sourceHtml = '';
    if (a.source_link) {
      const lblText = (a.type === 'visual') ? 'ORIGINAL NEWS · 原始新聞' : 'SOURCE · 原始連結';
      const linkText = a.source_title ? esc(a.source_title) : esc(a.source_link);
      sourceHtml = '<div class="source-link">'
        + '<span class="lbl">' + lblText + '</span>'
        + '<a href="' + esc(a.source_link) + '" target="_blank" rel="noopener">' + linkText + ' →</a>'
        + '</div>';
    }

    $('view-article').innerHTML = ''
      + '<button class="back-btn" onclick="window.BT.goBackFromArticle()">返回</button>'
      + '<article class="article-full">'
      +   '<div class="article-full-meta">'
      +     '<span><span class="persona-name">' + esc(a.persona) + '</span> · 版主 · <span class="type-tag">' + esc(typeLabel(a.type)) + '</span></span>'
      +     '<span>' + esc(a.timestamp) + '</span>'
      +   '</div>'
      +   '<h1 class="title">' + esc(a.title) + '</h1>'
      +   '<div class="content">' + esc(a.content) + '</div>'
      +   sourceHtml
      +   commentsHtml
      + '</article>';
  }

  // ============= 路由 =============
  function showView(viewId) {
    ['view-home', 'view-category', 'view-article'].forEach(id => {
      const el = $(id);
      if (el) el.hidden = (id !== viewId);
    });
    const v = $(viewId);
    if (v) {
      v.style.animation = 'none';
      void v.offsetHeight;
      v.style.animation = '';
    }
    window.scrollTo(0, 0);
  }

  function goHome() { location.hash = ''; }

  function goBackFromArticle() {
    if (currentCat) {
      location.hash = '#/cat/' + currentCat;
    } else if (history.length > 1) {
      history.back();
    } else {
      location.hash = '';
    }
  }

  function route() {
    const hash = location.hash || '';
    if (hash === '' || hash === '#' || hash === '#/') {
      currentCat = null;
      renderHome();
      showView('view-home');
    } else if (hash.indexOf('#/cat/') === 0) {
      const key = hash.split('/')[2];
      renderCategory(key);
      showView('view-category');
    } else if (hash.indexOf('#/article/') === 0) {
      const id = hash.split('/')[2];
      renderArticle(id);
      showView('view-article');
    } else {
      location.hash = '';
    }
  }

  window.BT = { goHome: goHome, goBackFromArticle: goBackFromArticle };
  window.addEventListener('hashchange', route);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', route);
  } else {
    route();
  }

  // ============= 防複製：複製時自動加浮水印 =============
  document.addEventListener('copy', function (e) {
    const sel = window.getSelection ? window.getSelection().toString() : '';
    if (!sel) return;
    const watermark = '\n\n——\n來源：' + SITE_NAME + ' · ' + SITE_URL;
    const stamped = sel + watermark;
    if (e.clipboardData) {
      e.clipboardData.setData('text/plain', stamped);
      e.preventDefault();
    }
  });

  // 阻擋右鍵選單（防右鍵複製）
  document.addEventListener('contextmenu', function (e) {
    const tag = (e.target && e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea') return;
    e.preventDefault();
  });
})();
</script>
</body>
</html>
"""



def generate_html(articles):
    """產生 index.html（雜誌風 SPA）"""
    today = datetime.now()
    update_time = today.strftime("%Y-%m-%d %H:%M")
    issue_label = f"VOL. {max(today.year - 2025, 1)} · ISSUE {today.month:02d}–{today.year}"

    # 整理文章資料：加上 id、cat
    enriched = []
    for i, a in enumerate(articles):
        if not a:
            continue
        # 影片・圖形類別：cat 強制設為 media
        if a.get("type") == "visual":
            cat = "media"
        else:
            cat = PERSONA_TO_CAT.get(a["persona"], "salon")
        enriched.append({
            "id": i,
            "persona": a["persona"],
            "cat": cat,
            "type": a["type"],
            "title": a["title"],
            "content": a["content"],
            "source_link": a.get("source_link"),
            "source_title": a.get("source_title"),
            "timestamp": a["timestamp"],
            "comments": a.get("comments", []),
        })

    # JSON 內若出現 </ 防呆（避免提早關閉 script 標籤）
    articles_json   = json.dumps(enriched, ensure_ascii=False).replace("</", "<\\/")
    categories = [
        {"key": "claude",  "name": "Claude",     "en": "Anthropic"},
        {"key": "chatgpt", "name": "ChatGPT",    "en": "OpenAI"},
        {"key": "gemini",  "name": "Gemini",     "en": "Google"},
        {"key": "grok",    "name": "Grok",       "en": "xAI"},
        {"key": "media",   "name": "VISUAL", "en": "Visual Records"},
        {"key": "salon",   "name": "SALON",      "en": "By Invitation"},
    ]
    categories_json = json.dumps(categories, ensure_ascii=False).replace("</", "<\\/")

    return (HTML_TEMPLATE
            .replace("{{UPDATE_TIME}}",     html.escape(update_time))
            .replace("{{ISSUE_LABEL}}",     html.escape(issue_label))
            .replace("{{ARTICLES_JSON}}",   articles_json)
            .replace("{{CATEGORIES_JSON}}", categories_json))


# ============================================================
# 主程式
# ============================================================
def main():
    start_time = datetime.now()
    print(f"========================================")
    print(f"  BLACK TOWER 開始運行（階段 2.1：雜誌風 + 影片・圖形）")
    print(f"  時間：{start_time}")
    print(f"  模型：{GEMINI_MODEL}（備援：{GEMINI_FALLBACK_MODEL}）")
    print(f"========================================")

    if not GOOGLE_API_KEY:
        print("⚠️  錯誤：GOOGLE_API_KEY 未設置，程式無法運行")
        return

    print(f"游泳池（帳號池）：{len(ACCOUNT_POOL)} 個帳號")
    print(f"策劃題庫：{len(CURATED_TOPICS)} 題")
    print(f"通用題庫：{len(ORIGINAL_TOPICS)} 題")
    print()

    all_articles = []
    used_topics = set()

    # ===== 主版：四版主各產 A 監控 + B 原創 =====
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
        article_b = generate_original_article(persona_name, persona, used_topics)
        if article_b:
            used_topics.add(article_b.get("topic_used", ""))
            print(f"        ✓ {article_b['title'][:40]}")
            print(f"  [評論] 生成中...")
            article_b["comments"] = generate_comments(article_b, persona)
            print(f"        ✓ {len(article_b['comments'])} 條評論")
            all_articles.append(article_b)
        else:
            print(f"        ✗ 失敗")
        print()

    # ===== 影片・圖形版：四版主輪流（每天 1 篇）=====
    print(f"────────  影片・圖形 版  ────────")
    persona_keys = list(PERSONAS.keys())
    # 用「日期 day-of-year」決定今天輪到誰，確保四人輪換
    today_idx = datetime.now().timetuple().tm_yday % len(persona_keys)
    chosen_persona_name = persona_keys[today_idx]
    chosen_persona = PERSONAS[chosen_persona_name]
    print(f"  本日輪值版主：{chosen_persona_name}")
    print(f"  生成 影片・圖形 文章...")
    article_v = generate_visual_article(chosen_persona_name, chosen_persona)
    if article_v:
        print(f"        ✓ {article_v['title'][:40]}")
        print(f"  [評論] 生成中...")
        article_v["comments"] = generate_comments(article_v, chosen_persona)
        print(f"        ✓ {len(article_v['comments'])} 條評論")
        all_articles.append(article_v)
    else:
        print(f"        ✗ 失敗（今日 RSS 無 AI 製圖／影片新聞，跳過）")
    print()

    random.shuffle(all_articles)

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
