# -*- coding: utf-8 -*-
"""
BLACK TOWER - 華人AI論壇自動化系統
階段 1：單頁文章流版本
- 全部使用 Google Gemini（免費 API）
- 四個版主用不同 system prompt 演不同個性
- A 類監控型：三塊拆解結構（事實 / 人味解讀 / 未來追問）
- B 類原創型：純觀點寫作
- 人工題目庫（高優先級）
- 春秋筆法：不點名大陸 AI、不碰政治
"""

import os
import random
import html
import time
from datetime import datetime
import requests
import feedparser


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
21. 可以討論：四大 AI（Claude、ChatGPT、Gemini、Grok）的
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

    content = call_gemini(messages, temperature=0.9, max_tokens=3500)
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

    content = call_gemini(messages, temperature=1.0, max_tokens=2500)
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
# 評論生成
# ============================================================
def generate_comments(article, persona):
    """生成 2-4 條評論"""
    num_comments = random.randint(2, 4)
    if len(ACCOUNT_POOL) < num_comments:
        return []
    selected_names = random.sample(ACCOUNT_POOL, num_comments)

    system_prompt = f"""你要扮演論壇上 {num_comments} 個普通網友，
針對版主「{persona['domain']}」的這篇文章寫評論。

{WRITING_RULES}

【評論規則】
- 每條評論 50~200 字，口語化
- 要有情緒：吐槽、反駁、認同、延伸、抬槓、冷笑、不耐煩
- {num_comments} 個網友口氣要不一樣
- 不准開頭寫「我同意」、「很有道理」、「個人覺得」這種 AI 廢話
- 直接切入話題，像真實人類在打字

【輸出格式】
每條評論一段，中間用 ===分隔=== 隔開。
不要加帳號名字、不要加編號、不要加說明文字。"""

    user_prompt = f"""【版主原文】
標題：{article['title']}

內容：
{article['content'][:2500]}

請以 {num_comments} 個不同網友身份寫 {num_comments} 條評論，用 ===分隔=== 隔開。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = call_gemini(messages, temperature=1.05, max_tokens=1500)
    if not result:
        return []

    parts = [p.strip() for p in result.split("===分隔===") if p.strip()]
    parts = parts[:num_comments]

    comments = []
    for i, comment_text in enumerate(parts):
        if i >= len(selected_names):
            break
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
    """產生 index.html"""
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
    print(f"  BLACK TOWER 開始運行（階段 1：單頁版）")
    print(f"  時間：{start_time}")
    print(f"  模型：{GEMINI_MODEL}（備援：{GEMINI_FALLBACK_MODEL}）")
    print(f"========================================")

    if not GOOGLE_API_KEY:
        print("⚠️  錯誤：GOOGLE_API_KEY 未設置，程式無法運行")
        return

    print(f"帳號池：{len(ACCOUNT_POOL)} 個帳號")
    print(f"策劃題庫：{len(CURATED_TOPICS)} 題")
    print(f"通用題庫：{len(ORIGINAL_TOPICS)} 題")
    print()

    all_articles = []
    used_topics = set()

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
