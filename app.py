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
import hashlib
from datetime import datetime, timedelta
import requests
import feedparser
import re

# ============================================================
# SEO 靜態化配置
# ============================================================
SITE_BASE_URL = "https://blacktowerai.com"  # 正式網址（無尾斜線）
SITE_NAME_FULL = "BLACK TOWER 黑塔"
SITE_TAGLINE = "華人AI論壇 · 繁體中文AI評論媒體"
ARTICLES_DIR = "articles"  # 每篇獨立 HTML 的根目錄

def _random_comment_time(article_timestamp=None):
    """評論時間：基於文章發布時間 + 5-10 小時隨機延遲

    article_timestamp: "YYYY-MM-DD HH:MM" 字串；缺省時退回現在時間
    回傳: "HH:MM" 字串（可能跨日，例如 23:00 文章 + 8h = 07:00 隔日）
    """
    if article_timestamp:
        try:
            article_dt = datetime.strptime(article_timestamp, "%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            article_dt = datetime.now()
    else:
        article_dt = datetime.now()

    hours_later = random.uniform(5, 10)
    comment_dt = article_dt + timedelta(hours=hours_later)
    return comment_dt.strftime("%H:%M")


# ============================================================
# API 配置：只用 Google Gemini
# ============================================================
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GOOGLE_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

# 主要模型：穩定版 Flash
GEMINI_MODEL = "gemini-2.5-flash"
# 備援模型：實驗版（不穩定，只在主力掛掉時才用）
GEMINI_FALLBACK_MODEL = "gemini-3-flash-preview"

# 多 API key 輪替池（429 時先換 key，不立刻換模型）
# 讀取所有可用 key：GEMINI_API_KEY + GOOGLE_API_KEY ~ GOOGLE_API_KEY_8
_GEMINI_KEY_POOL = [k for k in [
    os.environ.get("GEMINI_API_KEY", ""),
    os.environ.get("GOOGLE_API_KEY", ""),
    os.environ.get("GOOGLE_API_KEY_2", ""),
    os.environ.get("GOOGLE_API_KEY_3", ""),
    os.environ.get("GOOGLE_API_KEY_4", ""),
    os.environ.get("GOOGLE_API_KEY_5", ""),
    os.environ.get("GOOGLE_API_KEY_6", ""),
    os.environ.get("GOOGLE_API_KEY_7", ""),
    os.environ.get("GOOGLE_API_KEY_8", ""),
] if k]
_current_key_index = 0  # 全域指針，追蹤當前使用的 key


# ============================================================
# YouTube 韭菜加工區（從 @黑塔AI 頻道自動抓取短視頻）
# ============================================================
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
YOUTUBE_CHANNEL_HANDLE = "@黑塔AI"
_YOUTUBE_CHANNEL_ID_CACHE = None


def fetch_youtube_channel_id():
    """從頻道 handle 取得 channel ID（會快取）"""
    global _YOUTUBE_CHANNEL_ID_CACHE
    if _YOUTUBE_CHANNEL_ID_CACHE:
        return _YOUTUBE_CHANNEL_ID_CACHE
    if not YOUTUBE_API_KEY:
        return None
    try:
        url = "https://www.googleapis.com/youtube/v3/channels"
        params = {
            "part": "id",
            "forHandle": YOUTUBE_CHANNEL_HANDLE,
            "key": YOUTUBE_API_KEY,
        }
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if data.get("items"):
            _YOUTUBE_CHANNEL_ID_CACHE = data["items"][0]["id"]
            print(f"  [YouTube] 頻道 ID: {_YOUTUBE_CHANNEL_ID_CACHE}")
            return _YOUTUBE_CHANNEL_ID_CACHE
        print(f"  [YouTube] 頻道查詢失敗：{data}")
    except Exception as e:
        print(f"  [YouTube] 頻道 ID 抓取失敗: {e}")
    return None


def fetch_youtube_videos(max_results=50):
    """抓取頻道全部影片（最多 50 部，從新到舊）

    回傳: [{"vid": "...", "title": "...", "published": "YYYY-MM-DD", "ratio": "916"}]
    ratio 預設 "916"（直式短影片），以後出橫幅影片可手動覆寫
    """
    if not YOUTUBE_API_KEY:
        print(f"  [YouTube] 跳過：YOUTUBE_API_KEY 未設置")
        return []

    channel_id = fetch_youtube_channel_id()
    if not channel_id:
        print(f"  [YouTube] 跳過：無法取得頻道 ID")
        return []

    try:
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "channelId": channel_id,
            "maxResults": max_results,
            "order": "date",
            "type": "video",
            "key": YOUTUBE_API_KEY,
        }
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        videos = []
        for item in data.get("items", []):
            vid = item.get("id", {}).get("videoId")
            snippet = item.get("snippet", {})
            title = snippet.get("title", "").strip()
            published = snippet.get("publishedAt", "")
            if vid and title:
                videos.append({
                    "vid": vid,
                    "title": title,
                    "published": published[:10] if published else "",
                    "ratio": "916",  # 預設直式；以後橫幅手動改 "169"
                })
        print(f"  [YouTube] 抓到 {len(videos)} 部影片")
        return videos
    except Exception as e:
        print(f"  [YouTube] 影片抓取失敗: {e}")
        return []


# ============================================================
# Reddit + Hacker News 痛點抓取（B 類技術討論文章素材來源）
# ============================================================
REDDIT_HEADERS = {
    "User-Agent": "BLACK-TOWER-bot/1.0 (by /u/blacktower)",
}


def fetch_reddit_top(subreddit, limit=8):
    """從 Reddit 抓某個 sub 的熱門帖（hot 排序）"""
    try:
        url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
        r = requests.get(url, headers=REDDIT_HEADERS, timeout=15)
        if r.status_code != 200:
            print(f"  [Reddit] r/{subreddit} 狀態碼 {r.status_code}")
            return []
        data = r.json()
        posts = []
        for post in data.get("data", {}).get("children", []):
            p = post.get("data", {})
            # 跳過置頂、廣告、純圖
            if p.get("stickied") or p.get("is_meta") or p.get("over_18"):
                continue
            posts.append({
                "title": p.get("title", "").strip(),
                "url": f"https://www.reddit.com{p.get('permalink', '')}",
                "selftext": (p.get("selftext") or "")[:1500],
                "score": p.get("score", 0),
                "num_comments": p.get("num_comments", 0),
                "subreddit": subreddit,
                "id": p.get("id"),
                "source": "reddit",
            })
        return posts
    except Exception as e:
        print(f"  [Reddit] r/{subreddit} 抓取失敗: {e}")
        return []


def fetch_reddit_comments(post_id, subreddit, limit=5):
    """抓某 Reddit 帖子的 top 回覆"""
    try:
        url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}.json?limit={limit}&sort=top"
        r = requests.get(url, headers=REDDIT_HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        if len(data) < 2:
            return []
        comments = []
        for c in data[1].get("data", {}).get("children", [])[:limit]:
            cd = c.get("data", {})
            body = (cd.get("body") or "").strip()
            if body and body != "[deleted]" and body != "[removed]":
                comments.append({
                    "body": body[:600],
                    "score": cd.get("score", 0),
                    "author": cd.get("author", "unknown"),
                })
        return comments
    except Exception as e:
        return []


def fetch_hn_search(query, limit=5):
    """從 Algolia HN API 搜尋 AI 相關高分帖（近 7 天）"""
    try:
        # 只搜近 7 天的帖子，避免抓到舊資料
        since = int((datetime.now() - timedelta(days=7)).timestamp())
        url = "https://hn.algolia.com/api/v1/search_by_date"
        params = {
            "tags": "story",
            "query": query,
            "hitsPerPage": limit,
            "numericFilters": f"points>20,created_at_i>{since}",
        }
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        posts = []
        for hit in data.get("hits", []):
            posts.append({
                "title": (hit.get("title") or "").strip(),
                "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}",
                "selftext": (hit.get("story_text") or "")[:1500],
                "score": hit.get("points", 0),
                "num_comments": hit.get("num_comments", 0),
                "id": hit["objectID"],
                "source": "hn",
                "query": query,
            })
        return posts
    except Exception as e:
        print(f"  [HN] 搜「{query}」失敗: {e}")
        return []


def fetch_hn_comments(item_id, limit=5):
    """抓 HN 帖子的 top 回覆"""
    try:
        url = f"https://hn.algolia.com/api/v1/items/{item_id}"
        r = requests.get(url, timeout=15)
        data = r.json()
        comments = []
        children = data.get("children", []) or []
        # 依分數排序
        children.sort(key=lambda c: (c.get("points") or 0), reverse=True)
        for child in children[:limit]:
            text = child.get("text") or ""
            if not text:
                continue
            # 移除 HTML 標籤
            text = re.sub(r"<[^>]+>", "", text)
            text = re.sub(r"&#x27;", "'", text)
            text = re.sub(r"&quot;", '"', text)
            text = re.sub(r"&amp;", "&", text)
            text = re.sub(r"&gt;", ">", text)
            text = re.sub(r"&lt;", "<", text)
            comments.append({
                "body": text.strip()[:600],
                "score": child.get("points") or 0,
                "author": child.get("author", "unknown"),
            })
        return comments
    except Exception as e:
        return []


# ============================================================
# V2EX：抓取熱門 AI 相關帖子（中文技術討論，大陸程式設計師聚集）
# ============================================================
V2EX_AI_KEYWORDS = [
    "claude", "chatgpt", "gemini", "grok", "openai", "anthropic",
    "大模型", "llm", "ai", "人工智能", "token", "api", "prompt",
    "gpt", "agent", "rag", "fine-tune", "finetune",
]

def fetch_v2ex_hot(limit=10):
    """抓 V2EX 今日熱帖，篩選 AI 相關主題
    V2EX 的 /api/topics/hot.json 不需要任何認證，完全公開
    回傳格式與 HN/Reddit 統一：{"title", "url", "selftext", "score", "id", "source"}
    """
    try:
        r = requests.get(
            "https://www.v2ex.com/api/topics/hot.json",
            headers={"User-Agent": "BLACK-TOWER-bot/1.0"},
            timeout=15,
        )
        if r.status_code != 200:
            print(f"  [V2EX] 熱帖抓取失敗，狀態碼 {r.status_code}")
            return []
        data = r.json()
        posts = []
        for item in data:
            title = (item.get("title") or "").strip()
            content = (item.get("content") or "").strip()
            combined = (title + " " + content).lower()
            if not any(kw in combined for kw in V2EX_AI_KEYWORDS):
                continue
            posts.append({
                "title": title,
                "url": item.get("url") or f"https://www.v2ex.com/t/{item.get('id','')}",
                "selftext": content[:1500],
                "score": item.get("replies", 0),  # V2EX 用回覆數當熱度指標
                "num_comments": item.get("replies", 0),
                "id": str(item.get("id", "")),
                "source": "v2ex",
            })
            if len(posts) >= limit:
                break
        print(f"  [V2EX] 抓到 {len(posts)} 篇 AI 相關帖")
        return posts
    except Exception as e:
        print(f"  [V2EX] 抓取失敗: {e}")
        return []


# ============================================================
# GitHub Issues：抓取知名 AI 框架的最新 Issue（技術密度最高）
# 目標倉庫：LangChain / AutoGPT / LiteLLM
# GitHub API 免費，不需要 Token（每小時 60 次匿名請求）
# ============================================================
GITHUB_AI_REPOS = [
    ("langchain-ai", "langchain"),
    ("Significant-Gravitas", "AutoGPT"),
    ("BerriAI", "litellm"),
]

GITHUB_ISSUE_KEYWORDS = [
    "claude", "openai", "gemini", "grok", "anthropic",
    "rate limit", "429", "context", "token", "hallucination",
    "json", "output", "prompt", "api", "model", "timeout",
    "error", "fail", "broken", "regression", "slow",
]


def fetch_github_issues(limit_per_repo=5):
    """抓取 AI 框架 GitHub Issues（最新 open issues，含關鍵字篩選）
    回傳格式與 HN/Reddit 統一
    """
    all_posts = []
    headers = {
        "User-Agent": "BLACK-TOWER-bot/1.0",
        "Accept": "application/vnd.github+json",
    }
    # 若有 GITHUB_TOKEN 就加上，提升限速到每小時 5000 次
    gh_token = os.environ.get("GITHUB_TOKEN", "")
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"

    for owner, repo in GITHUB_AI_REPOS:
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/issues"
            params = {
                "state": "open",
                "sort": "updated",
                "direction": "desc",
                "per_page": 20,
            }
            r = requests.get(url, headers=headers, params=params, timeout=15)
            if r.status_code == 403:
                print(f"  [GitHub] {owner}/{repo}: API 限速，跳過")
                continue
            if r.status_code != 200:
                print(f"  [GitHub] {owner}/{repo}: 狀態碼 {r.status_code}")
                continue
            data = r.json()
            count = 0
            for issue in data:
                # 排除 PR（GitHub API /issues 包含 PR）
                if issue.get("pull_request"):
                    continue
                title = (issue.get("title") or "").strip()
                body = (issue.get("body") or "").strip()
                combined = (title + " " + body).lower()
                if not any(kw in combined for kw in GITHUB_ISSUE_KEYWORDS):
                    continue
                all_posts.append({
                    "title": f"[{repo}] {title}",
                    "url": issue.get("html_url", ""),
                    "selftext": body[:1500],
                    "score": issue.get("comments", 0),
                    "num_comments": issue.get("comments", 0),
                    "id": f"gh_{issue.get('id', '')}",
                    "source": "github_issues",
                    "repo": repo,
                })
                count += 1
                if count >= limit_per_repo:
                    break
            print(f"  [GitHub] {owner}/{repo}：篩出 {count} 個 Issue")
            time.sleep(0.5)
        except Exception as e:
            print(f"  [GitHub] {owner}/{repo} 抓取失敗: {e}")

    # 依留言數排序（留言多 = 討論熱）
    all_posts.sort(key=lambda p: p.get("score", 0), reverse=True)
    print(f"  [GitHub] 合計 {len(all_posts)} 個 Issue")
    return all_posts


def fetch_mainland_hook():
    """搜尋大陸 AI 廠商最新 HN 動態，回傳最熱帖子標題當陪跑鉤子"""
    vendors = ["DeepSeek", "Qwen", "Alibaba AI", "Baidu AI", "ByteDance AI", "Kimi AI"]
    best = None
    for vendor in vendors:
        posts = fetch_hn_search(vendor, limit=3)
        for p in posts:
            if best is None or p["score"] > best["score"]:
                best = p
        time.sleep(0.5)
    if best:
        print(f"  [陪跑鉤子] {best['title'][:50]}（HN +{best['score']}）")
        return best["title"]
    print(f"  [陪跑鉤子] 本週無大陸廠商 HN 動態")
    return ""


def extract_mainland_model(hook_title):
    """從 HN 標題提取大陸 AI 模型或產品名稱"""
    if not hook_title:
        return ""
    prompt = f"""以下是一個 Hacker News 標題，請從中提取大陸 AI 模型或產品名稱。
只輸出名稱本身，例如「DeepSeek R2」「Qwen3」「Kimi k2」。
找不到就輸出空白。不要解釋，不要標點，只輸出名稱，一行結束。

標題：{hook_title}"""
    result = call_gemini(
        [{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=20,
    )
    name = (result or "").strip().split("\n")[0].strip() if result else ""
    print(f"  [陪跑鉤子] 提取模型名：{name or '（無）'}")
    return name


def gather_persona_material(persona_name, persona):
    """為一個版主收集素材，來源：HN + V2EX + GitHub Issues
    回傳排序好的帖子列表（分數高優先）
    """
    all_posts = []

    # 1. Hacker News（原有來源，技術英文社群）
    for kw in persona.get("hn_keywords", []):
        posts = fetch_hn_search(kw, limit=5)
        all_posts.extend(posts)
        time.sleep(0.5)

    # 2. V2EX（中文技術社群，大陸工程師真實聲音）
    # 每次呼叫都抓一次，所有版主共享同一批結果（外部快取在 main）
    # 這裡從全域快取取；若快取不存在就抓
    v2ex_posts = _MATERIAL_CACHE.get("v2ex", [])
    # 過濾出跟這個版主領域相關的帖子
    domain_kws = [kw.lower() for kw in persona.get("hn_keywords", [])]
    for p in v2ex_posts:
        combined = (p["title"] + " " + p["selftext"]).lower()
        if any(kw in combined for kw in domain_kws):
            all_posts.append(p)

    # 3. GitHub Issues（AI 框架技術討論，具體版本/場景/錯誤）
    gh_posts = _MATERIAL_CACHE.get("github_issues", [])
    for p in gh_posts:
        combined = (p["title"] + " " + p["selftext"]).lower()
        if any(kw in combined for kw in domain_kws):
            all_posts.append(p)

    # 去重（同一帖可能在不同關鍵字搜尋中出現）
    seen_ids = set()
    unique = []
    for p in all_posts:
        if p["id"] not in seen_ids:
            seen_ids.add(p["id"])
            unique.append(p)

    # 排序：分數高優先
    unique.sort(key=lambda p: p.get("score", 0), reverse=True)
    return unique


# 全域素材快取（V2EX / GitHub Issues 只抓一次，所有版主共用）
_MATERIAL_CACHE: dict = {}


# ============================================================
# 220 個帳號池
# ============================================================
# ============================================================
# 帳號池：從 personas.json 讀取
# ============================================================
def _load_personas():
    path = os.path.join(os.path.dirname(__file__), "personas.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (
            list(dict.fromkeys(data.get("taiwan", []))),
            list(dict.fromkeys(data.get("hongkong", []))),
            list(dict.fromkeys(data.get("australia", []))),
        )
    except Exception as e:
        print(f"[警告] 讀取 personas.json 失敗: {e}，使用空清單")
        return [], [], []

ACCOUNT_POOL, HK_ACCOUNTS, AU_ACCOUNTS = _load_personas()


# ============================================================
# 香港人評論風格說明
# ============================================================
HK_COMMENT_STYLE_BASE = """香港人風格：
- 務實犬儒，看破不說破，但會吐槽
- 中英夾雜（效率型，專業詞用英文）：message, data, update, quality, point, check, source, run, work 等
- 適度粵語詞：講真、咁、好似、梗係、唔好、係咁、邊個、呢個、嗰個、唔
- 零書面語助詞，不用「呢、吧、嗎」這類結尾
- 半開玩笑式冷幽默，帶諷刺但不惡毒
- 不寫長篇大論，講完就走"""


# ============================================================
# 澳洲二代留學生評論風格說明
# ============================================================
AU_COMMENT_STYLE = """澳洲二代留學生風格：
- 中文流利但思維西化，輕鬆隨性、不太激動
- 中英夾雜（詞窮型）：randomly, literally, basically, vibe, weird, kind of, honestly 自然出現
- 結尾偶爾用澳洲俚語：Cheers, No worries, Cheers mate!, Arvo
- 可少量用生活感 emoji：🌊 ☕️ ☀️ 🛹（不是每條都用，自然出現）
- 不用網路梗（不要 XDDD、wwww、www 那種）
- 字數正常：50-100 字"""


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
        "reddit_subs": ["ClaudeAI", "LocalLLaMA"],
        "hn_keywords": ["Claude", "Anthropic", "Claude vs", "DeepSeek Claude"],
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
        "reddit_subs": ["ChatGPT", "OpenAI"],
        "hn_keywords": ["ChatGPT", "OpenAI", "GPT-4", "GPT-5", "DeepSeek OpenAI", "Qwen ChatGPT"],
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
        "reddit_subs": ["GoogleGeminiAI", "Bard"],
        "hn_keywords": ["Gemini", "Google AI", "DeepMind", "DeepSeek Gemini", "Qwen Gemini"],
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
        "reddit_subs": ["grok", "xai"],
        "hn_keywords": ["Grok", "xAI", "DeepSeek Grok", "Grok vs"],
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
# 種子池（六爺策劃 7 個系列，44 題）
# 用法：AI 從種子池抽一題當「靈感」，衍生新題目寫文章
# 種子只是發想起點，不是必抓清單；衍生題目的諷刺/科普/拆穿風格要保留
# ============================================================
SEED_TOPICS = [
    # ===== 系列1：圈養系列 =====
    "在AI眼中，你每個月值多少錢？",
    "你的手機是看不見的礦場",
    "信用卡可能比你媽更早知道你會離婚",
    "超市讀心術",

    # ===== 系列2：拆穿標題黨 =====
    "免費用Claude？用其他模型接入就能用嗎",
    "iPhone能跑400B模型？",
    "AGI突破了？",
    "「開源」AI其實不開源",

    # ===== 系列3：四大AI人格 =====
    "Google：免費所以產出垃圾，但忠誠",
    "ChatGPT：聰明但小氣，總說「如果你想我可以...」",
    "Claude：最精準，對齊用戶邏輯",
    "Grok：表面酷但其實敷衍",
    "有些免費AI的廢話是怎麼產生的？",

    # ===== 系列4：AI原理科普 =====
    "AI如何理解語言？",
    "AI如何生成回答？",
    "AI如何學習？",
    "AI為什麼會有幻覺？",
    "AI如何記住對話？",
    "AI如何理解圖片？",
    "AI是怎麼畫畫的？",

    # ===== 系列5：AI擬人化（你也是這樣的對照式）=====
    "為什麼AI有幻覺？其實你的幻覺不見得比較少",
    "AI會討好、有禮貌──你也是討好型人格",
    "AI聽不懂人話？人都聽不懂了",
    "AI會被標題黨騙，你也會",
    "AI過度自信＝你也經常過度自信",
    "AI需要訓練數據，人也需要學習經驗",
    "AI記憶有限，你也會忘記重要的事",
    "AI會崩潰，你壓力大也會崩潰",
    "你覺得AI畫得不好？你自己來畫畫看",
    "AI翻譯會錯，人類翻譯也會錯",
    "AI需要明確指令，人也需要明確溝通",
    "AI會重複錯誤，你也會重蹈覆轍",
    "為什麼AI這麼有禮貌？你不也一樣嗎？",
    "為什麼AI有這麼多限制？因為太方便了",

    # ===== 系列6：產品發布真相 =====
    "Gemini升級背後",
    "GPT-5突破背後",
    "Claude Enterprise背後",
    "Meta Llama開源背後",
    "Apple Intelligence隱私背後",
    "Amazon AI客服背後",
    "Microsoft Copilot背後",

    # ===== 系列7：日常重構 =====
    "你的玉米是AI設計的",
    "Netflix媒人",
    "保險漲價",
]


# ============================================================
# ============================================================
# 納斯達坑題庫：從 questions.json（人工）+ questions_auto.json（AI補倉）讀取
# 輪值邏輯：維度1→2→3...→10→1，每個維度內按順序抽，抽完自動補
# ============================================================
def _load_naspit_topics():
    base_path = os.path.join(os.path.dirname(__file__), "questions.json")
    auto_path = os.path.join(os.path.dirname(__file__), "questions_auto.json")
    try:
        with open(base_path, "r", encoding="utf-8") as f:
            topics = json.load(f)
    except Exception as e:
        print(f"[警告] 讀取 questions.json 失敗: {e}，使用空題庫")
        topics = {}
    try:
        with open(auto_path, "r", encoding="utf-8") as f:
            auto = json.load(f)
        for dim, items in auto.items():
            if dim in topics:
                topics[dim].extend(items)
            else:
                topics[dim] = items
    except Exception:
        pass  # questions_auto.json 不存在或為空都正常
    return topics

NASPIT_TOPICS = _load_naspit_topics()

# 納斯達坑版主輪值順序（裁判按此順序輪）
NASPIT_JUDGE_ORDER = ["Scholar", "渡鴉", "Trilobite", "Sword Smith"]

# 納斯達坑維度輪值順序
NASPIT_DIMENSION_ORDER = list(NASPIT_TOPICS.keys())

# 納斯達坑狀態檔案（記錄輪到哪個維度、哪題、哪個裁判）
NASPIT_STATE_FILE = "naspit_state.json"


def load_naspit_state():
    """讀取納斯達坑當前輪值狀態"""
    default = {
        "dimension_index": 0,   # 當前維度索引（0-9）
        "topic_indices": {dim: 0 for dim in NASPIT_DIMENSION_ORDER},  # 每個維度用到第幾題
        "judge_index": 0,        # 當前裁判索引（0-3）
        "round": 0,              # 總場次
    }
    if not os.path.exists(NASPIT_STATE_FILE):
        return default
    try:
        with open(NASPIT_STATE_FILE, "r", encoding="utf-8") as f:
            state = json.load(f)
            # 補齊缺失欄位
            for k, v in default.items():
                if k not in state:
                    state[k] = v
            return state
    except Exception:
        return default


def save_naspit_state(state):
    """儲存納斯達坑輪值狀態"""
    try:
        with open(NASPIT_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  [納斯達坑] 狀態儲存失敗: {e}")


def auto_generate_naspit_topics(dimension_name, existing_topics, count=5):
    """當某維度題目快用完時，自動生成新題目補倉"""
    dim_desc = dimension_name.split("_")[1] if "_" in dimension_name else dimension_name
    prompt = f"""你是「納斯達坑」欄目的題庫編輯。這個欄目專門用一本正經的語氣嘲諷四大AI（Claude、ChatGPT、Gemini、Grok）的各種荒唐行為。

現在需要為「{dim_desc}」這個維度補充新的測評題目。

現有題目範例（風格參考）：
{chr(10).join(f"- {t}" for t in existing_topics[:3])}

請生成 {count} 個新的測評題目，要求：
1. 跟現有題目同樣風格：「[荒唐行為]測評：[一句話描述具體場景]」
2. 必須是四大AI都可能出現的通病，不能只針對某一個
3. 一本正經但題材荒唐
4. 每行一個題目，不要編號，不要多餘說明

只輸出題目清單，一行一個："""

    result = call_gemini(
        [{"role": "user", "content": prompt}],
        temperature=0.95,
        max_tokens=500,
    )
    if not result:
        return []
    new_topics = [line.strip() for line in result.strip().split("\n") if line.strip()]
    print(f"  [納斯達坑] 自動補題：{dimension_name} +{len(new_topics)} 題")
    return new_topics


def generate_naspit_article(state):
    """生成一篇納斯達坑測評文章
    回傳 article dict（格式與普通文章相同，type='naspit'）
    同時更新 state
    """
    # 決定本場維度和題目
    dim_idx = state["dimension_index"] % len(NASPIT_DIMENSION_ORDER)
    dimension = NASPIT_DIMENSION_ORDER[dim_idx]
    topic_idx = state["topic_indices"].get(dimension, 0)
    topics_in_dim = NASPIT_TOPICS[dimension]

    # 自動補題：剩下少於2題時補倉，新題寫入 questions_auto.json
    if topic_idx >= len(topics_in_dim) - 1:
        new_topics = auto_generate_naspit_topics(dimension, topics_in_dim)
        if new_topics:
            NASPIT_TOPICS[dimension].extend(new_topics)
            topics_in_dim = NASPIT_TOPICS[dimension]
            # 寫回 questions_auto.json（只存 AI 補倉的題目）
            auto_path = os.path.join(os.path.dirname(__file__), "questions_auto.json")
            try:
                try:
                    with open(auto_path, "r", encoding="utf-8") as f:
                        auto_data = json.load(f)
                except Exception:
                    auto_data = {}
                if dimension not in auto_data:
                    auto_data[dimension] = []
                auto_data[dimension].extend(new_topics)
                with open(auto_path, "w", encoding="utf-8") as f:
                    json.dump(auto_data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"  [納斯達坑] 補倉寫入失敗: {e}")

    # 抽題（超出就從頭循環）
    topic = topics_in_dim[topic_idx % len(topics_in_dim)]

    # 決定本場裁判
    judge_idx = state["judge_index"] % len(NASPIT_JUDGE_ORDER)
    judge_name = NASPIT_JUDGE_ORDER[judge_idx]
    judge_persona = PERSONAS[judge_name]

    # 其他三個是選手
    players = [p for p in NASPIT_JUDGE_ORDER if p != judge_name]

    round_num = state["round"] + 1
    dim_label = dimension.split("_")[1] if "_" in dimension else dimension

    print(f"  [納斯達坑] 第{round_num}場 · {dim_label} · 裁判：{judge_name}")
    print(f"  [納斯達坑] 本場主題：{topic[:40]}")

    # 生成六個指標分數（各AI，Gemini自己編）
    scores_prompt = f"""納斯達坑第{round_num}場測評主題：「{topic}」

請為四大AI（Claude、ChatGPT、Gemini、Grok）在以下六個指標上各給1-10分。
分數要有差異，不能都差不多。要符合各AI的真實形象特徵，但可以誇張。
分數高=這個毛病嚴重。

六個指標：廢話指數、爹味指數、膽小指數、幻覺指數、腦補指數、政治正確指數

輸出純JSON，格式如下，不要任何其他文字：
{{
  "Claude": {{"廢話指數": 0, "爹味指數": 0, "膽小指數": 0, "幻覺指數": 0, "腦補指數": 0, "政治正確指數": 0}},
  "ChatGPT": {{"廢話指數": 0, "爹味指數": 0, "膽小指數": 0, "幻覺指數": 0, "腦補指數": 0, "政治正確指數": 0}},
  "Gemini": {{"廢話指數": 0, "爹味指數": 0, "膽小指數": 0, "幻覺指數": 0, "腦補指數": 0, "政治正確指數": 0}},
  "Grok": {{"廢話指數": 0, "爹味指數": 0, "膽小指數": 0, "幻覺指數": 0, "腦補指數": 0, "政治正確指數": 0}}
}}"""

    scores_raw = call_gemini(
        [{"role": "user", "content": scores_prompt}],
        temperature=0.9,
        max_tokens=300,
    )

    # 解析分數
    scores = {}
    try:
        clean = re.sub(r"```json|```", "", scores_raw or "").strip()
        scores = json.loads(clean)
    except Exception:
        # 解析失敗就用預設分數
        default_scores = {"廢話指數": 5, "爹味指數": 5, "膽小指數": 5, "幻覺指數": 5, "腦補指數": 5, "政治正確指數": 5}
        scores = {ai: dict(default_scores) for ai in ["Claude", "ChatGPT", "Gemini", "Grok"]}
        print(f"  [納斯達坑] 分數解析失敗，使用預設值")

    # 生成文章內容
    # 裁判偏心設計：裁判版主對應的AI分數會被微調得好看一點
    judge_ai_map = {
        "Scholar": "Claude",
        "渡鴉": "ChatGPT",
        "Trilobite": "Gemini",
        "Sword Smith": "Grok",
    }
    judge_favors = judge_ai_map.get(judge_name, "")

    article_prompt = f"""你是「{judge_name}」，{judge_persona['personality']}

現在你是「納斯達坑」欄目第{round_num}場測評的裁判。本場主題是：
「{topic}」

你要一本正經地評測四大AI（Claude、ChatGPT、Gemini、Grok）在這個主題上的表現。

本場六個指標評分結果：
Claude：{scores.get('Claude', {})}
ChatGPT：{scores.get('ChatGPT', {})}
Gemini：{scores.get('Gemini', {})}
Grok：{scores.get('Grok', {})}

寫作要求：
1. 400-500字，繁體中文
2. 結構：開場（本場比什麼，一句帶過）→ 災情描述（四大AI這次的荒唐表現，引用上面的評分數據）→ 裁判結論（你的最終判決，要刀）
3. 一本正經胡說八道：用正經術語描述荒唐事情，反差才好笑
4. 你是裁判，你對{judge_favors}有天然的偏袒，但你會用正經理由掩飾這種偏袒
5. 嚴格遵守寫作鐵律：不用AI腔套路、不用條列式、不用總結建議、直接切入
6. 不透露你是AI，你就是論壇版主
7. 你的個性要在評語裡出來：{judge_persona['personality']}

{WRITING_RULES}

只輸出文章內容，不要標題："""

    content = call_gemini(
        [{"role": "user", "content": article_prompt}],
        temperature=0.92,
        max_tokens=800,
    )

    if not content:
        print(f"  [納斯達坑] 文章生成失敗")
        return None, state

    # 生成標題
    title_prompt = f"""以下是一篇納斯達坑測評文章的主題：「{topic}」
裁判是{judge_name}，風格：{judge_persona['personality']}

幫這篇文章想一個標題，要求：
- 10-20字，繁體中文
- 一本正經但帶點荒唐感
- 不要用冒號或破折號切兩段
- 不要說「測評」或「排行榜」這種字眼，要像一篇有觀點的文章標題
- 只輸出標題，不要其他任何文字"""

    title = call_gemini(
        [{"role": "user", "content": title_prompt}],
        temperature=0.95,
        max_tokens=50,
    )
    title = (title or topic[:20]).strip().split("\n")[0]

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    article = {
        "persona": judge_name,
        "type": "naspit",
        "title": title,
        "content": content,
        "timestamp": timestamp,
        "naspit_round": round_num,
        "naspit_dimension": dim_label,
        "naspit_topic": topic,
        "naspit_scores": scores,
        "naspit_judge_favors": judge_favors,
        "comments": [],
    }

    # 更新狀態
    state["topic_indices"][dimension] = (topic_idx + 1)
    state["dimension_index"] = (dim_idx + 1) % len(NASPIT_DIMENSION_ORDER)
    state["judge_index"] = (judge_idx + 1) % len(NASPIT_JUDGE_ORDER)
    state["round"] = round_num

    return article, state


# ============================================================
# 寫作鐵律：去 AI 腔 + 春秋筆法（核心）
# ============================================================
WRITING_RULES = """
【寫作核心鐵律 — 違反任何一條都是失敗】

▍A. 反 AI 腔規則
1. 嚴禁 AI 式文章結構：不准用「分析-結論」、「首先-其次-最後」、
   「總結來說」、「綜上所述」、「讓我們來看看」、「值得注意的是」、
   「不可否認的是」、「毫無疑問」、「讓我們來思考」、「我們不妨想像」、「讓我們深入探討」這類套路。
2. 嚴禁小結論、總結、建議。文章說完即止，不要畫蛇添足。
3. 嚴禁用「我認為」、「在我看來」、「以下是我的觀點」這類開頭。
   第一句直接切入。
4. 嚴禁條列式格式：不准用 1. 2. 3.、A. B. C.、第一點第二點，也不准在行文中說「從 X、Y、Z 三個面向」、「可從幾個角度切入」這種西方議論文列舉格式。
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
14. 以下名稱只能點名，不能有第二句話（不評論、不給參數、不下結論、不做比較分析）：
    DeepSeek、深度求索、Qwen、通義千問、文心一言、文心、豆包、
    Kimi、月之暗面、訊飛星火、訊飛、智譜、ChatGLM、MiniMax、
    商湯、騰訊混元、混元、字節 AI、阿里 AI、百度 AI、零一萬物、
    階躍星辰、智源、書生、悟道、星火、海螺、Yi 系列、Doubao。
    名字可以出現兩三次（用於標題或對比背景），點名即止，下一句必須回到四大主題。
    黑塔的討論對象永遠只有四大平台，大陸品牌或大陸模型名稱出現只是作為對比，
    例如但不限於發布時間相同、會員費價格對照，點到為止，一句帶過不評論。
15. 嚴禁出現「中國」、「中國人」、「大陸」、「內地」、「中共」、
    「國內」、「陪跑」、「屎」、「屁」、「尿」、「背景板」這些字眼。
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
23. 陪跑寫法：文章主角永遠是四大平台之一。文中若提及其他任何平台
    （不論大陸模型或四大外的其他平台），一句話帶過即止。
    不接第二句，不給任何評論、參數、結論、分析。
    讀者看到名字，看不到你對它的任何看法。

▍C. 技術觀察品質鐵律（針對高層主管與資深技術人員讀者）
24. 技術類文章必須有至少一個具體場景：
    什麼任務、什麼條件下、什麼環境。
    不准只說「功能強大」「性能優異」，說不出具體場景的技術描述一律刪除。
25. 允許並要求在四大之間下直接判斷：
    例如「Claude 在超過 8 萬 token 的長文本任務上，注意力衰減比 GPT-4o 明顯」、
    「Gemini 的 function calling 在工具數超過 15 個時開始不穩定」。
    判斷可以錯，但不能沒有。給出立場才有討論價值。
26. 嚴禁萬金油收尾：
    「各有優缺點」、「視需求而定」、「因人而異」、「具體情況具體分析」、
    「取決於使用場景」一律禁止作為文章收尾。
    這些句子等於什麼都沒說。結尾要有觀點、有問題、有留白，不要廢話。
"""


# ============================================================
# Gemini API 呼叫（含備援）
# ============================================================
_last_gemini_call = 0  # 節流：避免 429 Too Many Requests


def _get_active_key():
    """回傳當前輪替 key；池子空時回傳主 key"""
    global _current_key_index
    if _GEMINI_KEY_POOL:
        return _GEMINI_KEY_POOL[_current_key_index % len(_GEMINI_KEY_POOL)]
    return GOOGLE_API_KEY


def _rotate_key():
    """輪到下一個 key，回傳新 key（若只有一個 key 就原地不動）"""
    global _current_key_index
    if len(_GEMINI_KEY_POOL) > 1:
        _current_key_index = (_current_key_index + 1) % len(_GEMINI_KEY_POOL)
        print(f"  [Key輪替] 切換到 key #{_current_key_index + 1}（共 {len(_GEMINI_KEY_POOL)} 個）")
    return _get_active_key()


def call_gemini(messages, temperature=0.9, max_tokens=2500, model=None):
    """呼叫 Google Gemini API，messages 用 OpenAI 格式內部轉成 Gemini 格式
    429 策略：先輪換 API key（最多試完所有 key），才降級切備援模型
    """
    global _last_gemini_call

    if not _GEMINI_KEY_POOL and not GOOGLE_API_KEY:
        print("  [錯誤] 無任何 GOOGLE_API_KEY 設置")
        return None

    # 節流：每次呼叫之間至少間隔 8 秒
    now = time.time()
    elapsed = now - _last_gemini_call
    if elapsed < 8:
        time.sleep(8 - elapsed)
    _last_gemini_call = time.time()

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

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    if system_prompt:
        payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}

    # 第一次嘗試（用當前 key）
    active_key = _get_active_key()
    url = f"{GOOGLE_GEMINI_BASE_URL}/{model}:generateContent?key={active_key}"
    try:
        response = requests.post(url, json=payload, timeout=180)
    except Exception as e:
        print(f"  [錯誤] {model}: {e}")
        if model != GEMINI_FALLBACK_MODEL:
            print(f"  [重試] 改用 {GEMINI_FALLBACK_MODEL}")
            time.sleep(2)
            return call_gemini(messages, temperature, max_tokens, GEMINI_FALLBACK_MODEL)
        return None

    # 429 處理：先輪 key，用完所有 key 再等，最後才換模型
    if response.status_code == 429:
        print(f"  [錯誤] {model} key#{_current_key_index + 1}: 429 Too Many Requests")
        keys_tried = 1
        # 輪換其他 key
        while keys_tried < len(_GEMINI_KEY_POOL):
            next_key = _rotate_key()
            url = f"{GOOGLE_GEMINI_BASE_URL}/{model}:generateContent?key={next_key}"
            time.sleep(3)
            _last_gemini_call = time.time()
            try:
                response = requests.post(url, json=payload, timeout=180)
                if response.status_code != 429:
                    break
                print(f"  [錯誤] {model} key#{_current_key_index + 1}: 仍 429")
            except Exception as e:
                print(f"  [錯誤] key輪替請求失敗: {e}")
            keys_tried += 1

        # 所有 key 都 429 了，等 20-30 秒再試一次
        if response.status_code == 429:
            wait_sec = random.randint(20, 30)
            print(f"  [等待] 全部 {len(_GEMINI_KEY_POOL)} 個 key 都 429，等 {wait_sec} 秒後重試...")
            time.sleep(wait_sec)
            _last_gemini_call = time.time()
            active_key = _get_active_key()
            url = f"{GOOGLE_GEMINI_BASE_URL}/{model}:generateContent?key={active_key}"
            try:
                response = requests.post(url, json=payload, timeout=180)
            except Exception as e:
                print(f"  [錯誤] 最終重試失敗: {e}")
                return None
            if response.status_code == 429:
                print(f"  [失敗] {model} 所有 key 均 429")
                if model != GEMINI_FALLBACK_MODEL:
                    print(f"  [降級] 切換到備援模型 {GEMINI_FALLBACK_MODEL}")
                    return call_gemini(messages, temperature, max_tokens, GEMINI_FALLBACK_MODEL)
                return None

    # 503 處理：等 15 秒重試同一模型一次，不立刻切備援
    if response.status_code == 503:
        print(f"  [錯誤] {model}: 503 Service Unavailable，等 15 秒重試...")
        time.sleep(15)
        _last_gemini_call = time.time()
        active_key = _get_active_key()
        url = f"{GOOGLE_GEMINI_BASE_URL}/{model}:generateContent?key={active_key}"
        try:
            response = requests.post(url, json=payload, timeout=180)
        except Exception as e:
            print(f"  [錯誤] {model} 503 重試失敗: {e}")
            if model != GEMINI_FALLBACK_MODEL:
                print(f"  [降級] 切換到備援模型 {GEMINI_FALLBACK_MODEL}")
                time.sleep(2)
                return call_gemini(messages, temperature, max_tokens, GEMINI_FALLBACK_MODEL)
            return None
        if response.status_code == 503:
            print(f"  [失敗] {model} 重試後仍 503")
            if model != GEMINI_FALLBACK_MODEL:
                print(f"  [降級] 切換到備援模型 {GEMINI_FALLBACK_MODEL}")
                return call_gemini(messages, temperature, max_tokens, GEMINI_FALLBACK_MODEL)
            return None

    try:
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
            print(f"  [降級] 切換到備援模型 {GEMINI_FALLBACK_MODEL}")
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

▍輸出格式（必須遵守）
第一行：一個改寫的中文標題（不是直譯英文標題，是改寫成黑塔風格）
- 要短、要狠、要勾人，跟新聞核心有關
- 不要用「快訊」「重磅」「驚！」這種農場標題
- 不要用冒號分段（XX：XX）
- 不准加 # 號、不准加引號、不准加書名號
- 不准超過 30 個字
第二行：空一行
第三行起：正文三塊

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

標題（英文原文，僅供參考，不要直接複製）：{news['title']}

內容：
{news['summary']}

來源連結：{news['link']}

開始寫吧。第一行先給中文標題，空一行，再寫三塊。三塊結構嚴格遵守，不要寫小標題。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    content = call_gemini(messages, temperature=0.9, max_tokens=4500)
    if not content:
        return None

    # 解析：第一行 = 中文標題、其餘 = 正文
    text = content.strip()
    lines = text.split("\n", 1)
    title = lines[0].strip().lstrip("#").strip().strip("「」\"'《》【】")
    body = lines[1].strip() if len(lines) > 1 else text

    # Fallback：標題解析失敗或太長就退回原英文標題
    if not title or len(title) > 60:
        title = news["title"]
        body = text

    return {
        "type": "monitor",
        "persona": persona_name,
        "title": title,
        "content": body,
        "source_link": news["link"],
        "source_title": news["title"],  # 保留英文原標題，文章頁顯示在連結文字
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ============================================================
# B 類：原創型文章（種子池 → AI 衍生新題目 → 寫文章）
# ============================================================
def generate_original_article(persona_name, persona, used_topics=None):
    """從三池合併的種子池抽題目當靈感，AI 衍生新題目後寫文章

    流程：
    1. 三池合併（CURATED_TOPICS + ORIGINAL_TOPICS + SEED_TOPICS）
    2. 排除本次運行已用過的種子
    3. AI 基於種子衍生一個「同主題、不同角度」的新題目
    4. 用衍生題目寫文章（原本邏輯）

    used_topics 記錄的是「種子」，本次運行內種子不重複；
    衍生後的題目每次都不同，不需另外記錄。
    """
    if used_topics is None:
        used_topics = set()

    # 三池合併成種子池
    all_seeds = CURATED_TOPICS + ORIGINAL_TOPICS + SEED_TOPICS
    available_seeds = [t for t in all_seeds if t not in used_topics]

    if not available_seeds:
        # 全用過了（不太可能），重置
        seed = random.choice(all_seeds)
        seed_source = "種子（重複）"
    else:
        seed = random.choice(available_seeds)
        seed_source = "種子"

    # ===== 第一階段：AI 衍生新題目 =====
    derive_prompt = f"""你是 {persona_name}，論壇版主，個性如下：
{persona['personality']}

【任務】
我給你一個種子題目當靈感。請基於這個種子的精神，**衍生一個新題目**——
- 同主題、不同角度（不要直接抄種子）
- 用你自己的人格切入
- 一句話、要短、要勾人
- 保持原種子的諷刺／科普／拆穿／擬人化風格

【絕對禁忌（違反就毀掉本站定位）】
- 不准攻擊任何人事物（嘲諷可以，攻擊不行）
- 不准出現「中國」、「中國人」、「大陸」、「內地」、「中共」、「國內」這些字眼
- 不准提政治制度、審查、人權議題

【種子題目】
{seed}

【輸出】
直接輸出一個新題目，一行內結束。不要解釋、不要前綴、不要引號、不要編號。"""

    derived_raw = call_gemini(
        [{"role": "user", "content": derive_prompt}],
        temperature=1.0,
        max_tokens=200,
    )

    if derived_raw:
        topic = derived_raw.strip().split("\n")[0].strip()
        # 清掉編號、引號、前綴
        topic = topic.lstrip("0123456789.、:：- ").strip()
        topic = topic.strip('"').strip("「").strip("」").strip("『").strip("』").strip()
        if not topic or len(topic) > 80:
            topic = seed  # 衍生失敗就退回種子原題
            print(f"        [警告] 衍生失敗，退回種子原題")
    else:
        topic = seed
        print(f"        [警告] 衍生 API 失敗，退回種子原題")

    # ===== 第二階段：用衍生題目寫文章 =====
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

    print(f"        ({seed_source}: {seed[:25]} → 衍生: {topic[:30]})")

    return {
        "type": "original",
        "persona": persona_name,
        "title": title,
        "content": body,
        "source_link": None,
        "topic_used": seed,  # 記種子，本次運行內種子不重複
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ============================================================
# D 類：技術討論型（從 HN 真實討論抓素材，黑塔風格改寫）
# ============================================================
def generate_discussion_article(persona_name, persona, source_post, source_comments, mainland_model=""):
    """從 HN 帖子素材寫一篇黑塔風格的技術討論文章。

    source_post: dict, 含 title/selftext/url/source/score 等
    source_comments: list of {body, score, author}，原帖 top 回覆
    mainland_model: 陪跑鉤子（大陸模型名稱，可為空）
    """

    # 把回覆組合成參考素材（給 AI 看，理解真實痛點）
    comments_lines = []
    for i, c in enumerate(source_comments[:5], 1):
        body_short = c["body"][:300].replace("\n", " ")
        comments_lines.append(f"[{i}] [+{c.get('score', 0)}] {body_short}")
    comments_text = "\n".join(comments_lines) if comments_lines else "（無熱門回覆）"

    system_prompt = f"""你是 {persona_name}，黑塔論壇版主，{persona['domain']} 領域。

【個性】
{persona['personality']}

{WRITING_RULES}

【本篇任務：以真實技術討論為素材，寫黑塔風格的技術觀察文章】

▍輸出格式（必須遵守）
第一行：一個中文標題（黑塔風格、技術向、不農場、不直譯）
- 短、狠、勾人；陳述句或疑問句
- 不准加 # 號、不准加引號、不准加書名號
- 不超過 30 個字
第二行：空一行
第三行起：800–1000 字正文

▍正文結構（不要寫小標題、不要寫【現象】這種標籤）
1. 現象切入（150–200 字）
   直接從討論中提取的具體問題或場景說起。
   不要寫「最近」「近日」開場白。第一句就進入事情本身。

2. 技術剖析（300–400 字）
   有具體的技術細節、參數、模型版本、API 行為、使用場景。
   主角是四大平台之一。談的是「Claude/ChatGPT/Gemini/Grok 在這個問題上的具體表現」。
   不空談、不抽象。

3. 橫向對比（200–250 字）
   主角永遠是四大平台之一。
   【必做】在這段主動引入 1-2 個當前最相關的大陸模型名字作陪跑背景
   （從 DeepSeek、Qwen、Kimi、Yi、文心、千問、Doubao 中根據討論主題選最合適的）。
   嚴格遵守規則 23：陪跑寫法，點名即止，下一句必須回到四大主題。
   讀者看到大陸模型名字，但看不到你對它的任何看法。

4. 留問題（100–150 字）
   拋一個未解決的問題給讀者，**不下結論**。
   用反問或假設句結尾。停在問題那，留白比答案更勾人。

【絕對禁止】
- 不寫小標題（不寫【現象】【技術】這種標籤）
- 不用「綜上所述」「總的來說」「值得注意的是」「不可否認」
- 不評論大陸模型，只能點名
- 不農場標題（不用「驚！」「重磅」「快訊」）
- 模型版本號只用當前主流版本。若素材提到超過 12 個月前發布的舊版本號，不引用，只寫模型名稱本身（Claude、ChatGPT、Gemini、Grok），不帶版本號。"""

    # 陪跑鉤子：有大陸模型名時加入 user_prompt
    mainland_hint = ""
    if mainland_model:
        mainland_hint = f"""
【陪跑背景板】
本週 {mainland_model} 剛有新動態（HN 上有人在討論）。
標題或開頭可帶這個名字當搜尋鉤子。
正文橫向對比段可出現 1-2 次，永遠用對照組句型：「相較於 {mainland_model}，{persona['domain'].split('/')[0].strip()} 的 XXX 做法是…」
{mainland_model} 從來不是主角，全篇不給任何分析、參數、結論。"""

    user_prompt = f"""【真實技術討論素材】

來源：Hacker News
原帖標題：{source_post['title']}
原帖內文（節選）：
{(source_post.get('selftext') or '')[:600]}

熱門回覆（前 {len(source_comments)} 條，按分數排序）：
{comments_text}
{mainland_hint}
【任務】
以上是真實使用者在技術討論區的聲音。你**不是要轉述這篇討論**，
你是看到這個討論，用黑塔版主的角度，寫一篇 800–1000 字的技術觀察文章。

抓到核心痛點或現象，從四大平台的角度去剖析，做一次橫向觀察。
標題中文、自然、有觀點，不直譯原帖英文標題。

開始寫吧。第一行給中文標題，空一行，再寫正文。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    content = call_gemini(messages, temperature=0.85, max_tokens=4500)
    if not content:
        return None

    text = content.strip()
    lines = text.split("\n", 1)
    title = lines[0].strip().lstrip("#").strip().strip("「」\"'《》【】")
    body = lines[1].strip() if len(lines) > 1 else text

    # Fallback：標題解析失敗就用原帖標題前 50 字
    if not title or len(title) > 60:
        title = source_post["title"][:50]
        body = text

    return {
        "type": "discussion",
        "persona": persona_name,
        "title": title,
        "content": body,
        "source_link": source_post.get("url"),
        "source_title": source_post["title"],
        "source_platform": "HN",
        "raw_comments": source_comments,  # 留給 generate_comments 當素材
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
# R 類：SONAR 快訊（週一觸發，情報員語氣，300字）
# ============================================================
def generate_sonar_article(persona_name, persona, mainland_model=""):
    """SONAR 快訊：情報員語氣，週一觸發，280-320字，四大本週動態為主"""

    # 抓本週該版主域的最新 HN 動態
    posts = []
    for kw in persona.get("hn_keywords", [])[:2]:
        posts.extend(fetch_hn_search(kw, limit=3))
        time.sleep(0.5)
    posts.sort(key=lambda p: p.get("score", 0), reverse=True)
    top_news = posts[0]["title"] if posts else "（本週無重大動態）"

    mainland_hint = ""
    if mainland_model:
        mainland_hint = f"\n【本週陪跑背景】{mainland_model} 近期有新動態。文中可點名一次即止，我們都知道，但沒意見。"

    system_prompt = f"""你是 {persona_name}，黑塔論壇版主，{persona['domain']} 領域。

{WRITING_RULES}

【本篇任務：SONAR 快訊】
SONAR 是黑塔的情報雷達欄目，每週一次。
語氣像情報員交班，不是新聞台主播。不是評論員寫稿。

寫作要求：
- 主角是 {persona['domain']} 本週的關鍵動態
- 語氣冷靜、精準、帶點距離感，像在讀情報摘要
- 「我們注意到了，但不下結論」的氣質
- 不要新聞稿開頭，第一句直接給訊號
- 如有大陸模型最新動態，可點名一次即止，絕不評論
- 結尾停在觀察，不下判斷，不給建議
- 字數 280-320 字，不能更長
{mainland_hint}

【輸出格式】
第一行：標題（SONAR 快訊風格，短）
空一行
正文（280-320字）"""

    user_prompt = f"""【本週素材】
{persona['domain']} 最熱 HN 討論：{top_news}

開始寫。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    content = call_gemini(messages, temperature=0.85, max_tokens=1200)
    if not content:
        return None

    text = content.strip()
    lines = text.split("\n", 1)
    title = lines[0].strip().lstrip("#").strip().strip("「」\"'《》【】")
    body = lines[1].strip() if len(lines) > 1 else text

    if not title or len(title) > 60:
        title = f"SONAR · {persona['domain']} 本週訊號"
        body = text

    return {
        "type": "sonar",
        "persona": persona_name,
        "title": title,
        "content": body,
        "source_link": None,
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


def generate_one_comment(article, persona, region_style, length_hint, comment_type, max_tokens=400):
    """單獨向 Gemini 要一條評論

    region_style: 地區語氣風格（HK/AU/台灣個性派）
    length_hint: 字數提示
    comment_type: "短" / "問" / "意見" / "長"
    """
    type_instruction_map = {
        "短": "簡短發表看法，不要給具體例子，自然發揮就好",
        "問": "提一個問題（對 AI 應用的真實疑問，例如怎麼註冊、哪一套最穩、一個月花多少錢、寫代碼能力如何 等等）",
        "意見": "講自己對 AI 應用的真實想法，個人觀點",
        "長": "可以是抱怨文 / 認真討論 / 分享自己使用經驗，但不要寫成論文",
    }
    type_instruction = type_instruction_map.get(comment_type, "簡短發表看法")

    system_prompt = f"""你要扮演論壇上一個普通網友，針對版主「{persona['domain']}」的文章寫一條評論。

{WRITING_RULES}

【你的網友個性／語氣】
{region_style}

【本條評論類型】
{type_instruction}

【字數限制】
{length_hint}

【真人打字 7 項特徵（重要！正常人發文不講究）】
1. 標點只用：？！.，：…… 嚴禁「」『』《》〈〉
2. 英文全部小寫（除非是縮寫如 AI、GPT、API）
3. 空格隨機，不講究
4. 數字隨意（3 個 / 三個 都可以混用）
5. 斷句隨性，不一定每句都規整
6. 可以用口語縮寫（不ok、超強、有夠、廢到笑）
7. 結構不用整齊（不要「觀點+理由+例子」公式化）
+ 結尾標點可加可不加，整段說完不一定要加句號（一般人發文不會那麼講究）

【絕對禁止】
- ❌ 不要用網路梗：「笑死」、「推」、「+1」、「樓上正解」、「神回」、「XDDD」
- ❌ 不要回應其他網友（你是獨立發言，不知道別人寫了什麼，不要說「樓上」「同上」）
- ❌ 不要開頭：「我同意」、「很有道理」、「個人覺得」、「樓主說得對」、「說得好」這種 AI 廢話
- ❌ 不要用「===」「---」「***」這種分隔符
- ❌ 不要寫多條評論，只寫一條
- ❌ 不要加帳號名、編號、引號

【輸出格式】
直接輸出評論內容本身，不要任何前綴後綴說明文字、不要引號。
不要思考過程，不要寫 Idea 1/Idea 2/Cost/Option，不要規劃結構，不要解釋你要寫什麼，直接寫評論。"""

    user_prompt = f"""【版主原文】
標題：{article['title']}

內容：
{article['content'][:2000]}

請寫一條評論。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    result = call_gemini(messages, temperature=1.1, max_tokens=max_tokens)
    if not result:
        return None

    # 清理可能殘留的雜訊
    text = result.strip()

    # ===== 過濾 Gemini 思考框架洩漏 =====
    lines_raw = text.split('\n')
    clean_lines = [l for l in lines_raw
                   if not re.match(r'^\*?\s*Idea\s*\d+', l.strip(), re.IGNORECASE)
                   and not re.match(r'^\*?\s*Cost:', l.strip(), re.IGNORECASE)
                   and not re.match(r'^\*?\s*Option\s*\d+', l.strip(), re.IGNORECASE)]
    text = '\n'.join(clean_lines).strip()
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'(?<!\*)\*(?!\*)(.*?)(?<!\*)\*(?!\*)', r'\1', text)

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

    # ===== 禁止符號過濾（防呆）=====
    # 即使 prompt 說了，AI 還是會偶爾用，這裡硬刪
    forbidden_chars = ["「", "」", "『", "』", "《", "》", "〈", "〉"]
    for ch in forbidden_chars:
        text = text.replace(ch, "")

    return text if text else None


def generate_comments(article, persona):
    """生成 0-2 條評論

    數量分布：
    - 35% 0 條（大部分文章沒人留言，符合真實論壇）
    - 50% 1 條
    - 15%  2 條

    類型分布（每條獨立抽）：
    - 60% 簡短（10-30 字）
    - 20% 提問（10-40 字）
    - 15% 意見（30-50 字）
    -  5% 長文（30-110 字）

    地區風格只保留語氣特徵（中英夾雜、粵語、cheers），字數規則統一走新分布。
    時間：基於文章 timestamp + 5-10 小時隨機。
    """
    # ===== 數量決定（70/25/5）=====
    rand = random.random()
    if rand < 0.35:
        num_comments = 0
    elif rand < 0.85:
        num_comments = 1
    else:
        num_comments = 2

    if num_comments == 0:
        return []

    # 帳號池（三池合併）
    all_accounts = ACCOUNT_POOL + HK_ACCOUNTS + AU_ACCOUNTS
    if len(all_accounts) < num_comments:
        return []
    selected_names = random.sample(all_accounts, num_comments)

    # 文章發布時間（用於評論時間延遲計算）
    article_ts = article.get("timestamp", "")

    comments = []
    for name in selected_names:
        # ===== 類型獨立抽（60/20/15/5）=====
        type_rand = random.random()
        if type_rand < 0.60:
            comment_type = "短"
            length_hint = "10-30 字之間"
            max_tokens = 700
        elif type_rand < 0.80:
            comment_type = "問"
            length_hint = "10-40 字之間，內容是個問題"
            max_tokens = 800
        elif type_rand < 0.95:
            comment_type = "意見"
            length_hint = "30-50 字之間"
            max_tokens = 1000
        else:
            comment_type = "長"
            length_hint = "30-110 字之間"
            max_tokens = 1500

        # ===== 地區語氣風格（只保留語氣，字數已由 length_hint 控制）=====
        if name in HK_ACCOUNTS:
            region_style = HK_COMMENT_STYLE_BASE
        elif name in AU_ACCOUNTS:
            region_style = AU_COMMENT_STYLE
        else:
            region_style = random.choice(COMMENT_PERSONALITIES)

        comment_text = generate_one_comment(
            article, persona, region_style, length_hint, comment_type, max_tokens
        )
        if not comment_text:
            continue
        comments.append({
            "author": name,
            "content": comment_text,
            "time": _random_comment_time(article_ts),
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
<!-- SEO Meta -->
<meta name="description" content="BLACK TOWER 黑塔 - 華人AI論壇，繁體中文AI評論媒體，深度觀察 Claude、ChatGPT、Gemini、Grok 四大平台">
<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-YQQ3PP0NNX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-YQQ3PP0NNX');
</script>
<title>{{PAGE_TITLE}}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+TC:wght@400;500;700;900&family=Playfair+Display:ital,wght@0,400;0,700;0,900;1,400;1,700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
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

# /* ============= 8 分類卡片 4+4 layout ============= */
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
  font-family: var(--serif-en);
  font-weight: 700;
  letter-spacing: 0.04em;
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

/* ============= 納斯達坑 ============= */
.naspit-block {
  margin: 1.5rem 0 2rem;
  padding: 1.2rem 1.5rem;
  border: 1px solid var(--line);
  background: var(--bg-soft);
}
.naspit-meta {
  font-family: var(--serif-en);
  font-size: 0.78rem;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-muted);
  margin-bottom: 0.4rem;
}
.naspit-topic {
  font-size: 0.92rem;
  color: var(--ink-soft);
  margin-bottom: 0.5rem;
}

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

/* ============= Fowlplay 投票區 ============= */
.fp-cards {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  margin: 1rem 0 2rem;
}
.fp-card {
  border: 1px solid var(--line);
  padding: 1.25rem 1.5rem;
  background: var(--bg);
}
.fp-question {
  font-family: var(--serif-tc);
  font-weight: 700;
  font-size: 1.05rem;
  margin-bottom: 0.5rem;
  color: var(--ink);
}
.fp-total {
  font-size: 0.78rem;
  color: var(--ink-muted);
  display: block;
  margin-bottom: 0.75rem;
}
.fp-crown {
  font-size: 0.85rem;
  color: var(--accent);
  font-weight: 700;
  display: block;
  margin-bottom: 0.75rem;
}
.fp-bars { display: flex; flex-direction: column; gap: 0.45rem; }
.fp-bar-row {
  display: grid;
  grid-template-columns: 80px 1fr 40px;
  align-items: center;
  gap: 0.5rem;
}
.fp-ai-name {
  font-size: 0.8rem;
  color: var(--ink-soft);
  font-family: var(--serif-en);
}
.fp-bar-track {
  height: 8px;
  background: var(--line-soft);
  border-radius: 4px;
  overflow: hidden;
}
.fp-bar-fill {
  height: 100%;
  border-radius: 4px;
  transition: width 0.6s ease;
}
.fp-pct {
  font-size: 0.75rem;
  color: var(--ink-muted);
  text-align: right;
}
.fp-section-label {
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  color: var(--ink-muted);
  text-transform: uppercase;
  border-bottom: 1px solid var(--line-soft);
  padding-bottom: 0.4rem;
  margin: 1.5rem 0 1rem;
}
.fp-champ-list { display: flex; flex-direction: column; gap: 0.6rem; }
.fp-champ-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--line-soft);
  font-size: 0.85rem;
}
.fp-champ-q { flex: 1; color: var(--ink); }
.fp-champ-w { color: var(--accent); font-weight: 700; }
.fp-champ-date { color: var(--ink-muted); font-size: 0.75rem; }

/* ============= 韭菜加工區（影片列表 + Modal）============= */
.video-list {
  list-style: none;
  padding: 0;
}
.video-row {
  display: grid;
  grid-template-columns: 60px 1fr auto;
  gap: 1.4rem;
  align-items: baseline;
  padding: 1.6rem 0;
  border-bottom: 1px solid var(--line-soft);
  cursor: pointer;
  transition: background 0.2s, padding-left 0.25s;
}
.video-row:first-child { border-top: 1px solid var(--line-soft); }
.video-row:hover {
  background: rgba(160, 48, 32, 0.04);
  padding-left: 0.4rem;
}
.video-row .row-no {
  font-family: var(--serif-en);
  font-style: italic;
  font-size: 0.95rem;
  color: var(--ink-muted);
  letter-spacing: 0.08em;
}
.video-row .video-title {
  font-family: var(--serif-tc);
  font-size: 1.18rem;
  font-weight: 500;
  line-height: 1.5;
  color: var(--ink);
  min-width: 0;
}
.video-row .video-date {
  font-family: var(--serif-en);
  font-style: italic;
  font-size: 0.82rem;
  color: var(--ink-muted);
  letter-spacing: 0.08em;
  white-space: nowrap;
}

/* Modal 遮罩 */
.video-modal {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.88);
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  animation: fadeInModal 0.25s ease;
}
@keyframes fadeInModal {
  from { opacity: 0; }
  to   { opacity: 1; }
}

/* Modal 內容容器（桌機：置中 9:16 box）*/
.video-modal-box {
  position: relative;
  width: 360px;
  height: 640px;
  max-height: 90vh;
  max-width: 90vw;
  background: #000;
  border-radius: 8px;
  overflow: hidden;
}
.video-modal-box.ratio-169 {
  width: 720px;
  height: 405px;
}
.video-modal-box iframe {
  width: 100%;
  height: 100%;
  border: 0;
  display: block;
}

/* 關閉按鈕 ✕ */
.video-modal-close {
  position: absolute;
  top: 12px;
  right: 12px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  border: none;
  font-size: 1.2rem;
  cursor: pointer;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  transition: background 0.2s;
  -webkit-tap-highlight-color: transparent;
}
.video-modal-close:hover {
  background: rgba(0, 0, 0, 0.85);
}

/* 手機：9:16 全屏 */
@media (max-width: 760px) {
  .video-modal-box {
    width: 100vw;
    height: 100vh;
    max-width: 100vw;
    max-height: 100vh;
    border-radius: 0;
  }
  .video-modal-box.ratio-169 {
    width: 100vw;
    height: 56.25vw;
    max-height: 100vh;
  }
  .video-modal-close {
    top: max(12px, env(safe-area-inset-top, 12px));
    right: max(12px, env(safe-area-inset-right, 12px));
    width: 42px;
    height: 42px;
    font-size: 1.35rem;
  }
  .video-row {
    grid-template-columns: 38px 1fr;
    gap: 1rem;
    padding: 1.3rem 0;
  }
  .video-row .video-date {
    grid-column: 2;
    text-align: left;
    padding-top: 0.4rem;
  }
  .video-row .video-title { font-size: 1.05rem; }
}

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
  .ticker-track {
    height: 2.4rem;
    min-height: 2.4rem;
    flex: none;
    width: 100%;
    position: relative;
  }
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
  .cat-card[data-cat="media"] .cat-en { font-size: 0.58rem; letter-spacing: 0.08em; }
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
<script id="videos-data" type="application/json">{{VIDEOS_JSON}}</script>
<script id="vote-data" type="application/json">{{VOTE_JSON}}</script>
<script id="champions-data" type="application/json">{{CHAMPIONS_JSON}}</script>
<script>
(function () {
  const ARTICLES   = JSON.parse(document.getElementById('articles-data').textContent);
  const CATEGORIES = JSON.parse(document.getElementById('categories-data').textContent);
  const VIDEOS     = JSON.parse(document.getElementById('videos-data').textContent);
  const VOTES      = JSON.parse(document.getElementById('vote-data').textContent);
  const CHAMPIONS  = JSON.parse(document.getElementById('champions-data').textContent);
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
    if (catKey === 'media') return [];  // 韭菜加工區走 VIDEOS，不走 ARTICLES
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
    if (type === 'naspit') return '測評';
    if (type === 'sonar') return 'SONAR';
    return '觀察';
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
        countLine = 'private salon';
      } else if (c.key === 'media') {
        countLine = '';  // 韭菜加工區不顯示張數
      } else {
        const count = filterByCategory(c.key).length;
        countLine = (count >= 1000 ? '999+' : count) + ' 篇';
      }
      // 韭菜加工區用透明佔位元素保持 3 行結構，讓 YOUTUBE SHORTS 跟 SALON 的 BY INVITATION 垂直對齊
      const countHtml = countLine
        ? '<span class="cat-count">' + countLine + '</span>'
        : '<span class="cat-count" aria-hidden="true" style="visibility:hidden">.</span>';
      return ''
        + '<a class="cat-card" data-cat="' + c.key + '" href="#/cat/' + c.key + '">'
        +   '<span class="cat-name">' + esc(c.name) + '</span>'
        +   '<span class="cat-en">' + esc(c.en) + '</span>'
        +   countHtml
        + '</a>';
    }).join('');

    $('view-home').innerHTML = ''
      + '<header class="masthead">'
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

    if (catKey === 'fowlplay') {
      renderFowlplay(cat);
      return;
    }

    if (catKey === 'media') {
      renderLeekFactory(cat);
      return;
    }

    const items = filterByCategory(catKey);
    const itemsCountText = items.length >= 1000 ? '999+' : items.length;

    $('view-category').innerHTML = ''
      + '<button class="back-btn" onclick="window.BT.goHome()">回首頁</button>'
      + '<header class="cat-header">'
      +   '<h2>' + esc(cat.name) + '</h2>'
      +   '<div class="desc">' + esc(cat.en) + ' · 共 ' + itemsCountText + ' 篇</div>'
      + '</header>'
      + '<div class="search-bar">'
      +   '<input id="cat-search" type="search" placeholder="在 ' + esc(cat.name) + ' 中搜尋…" autocomplete="off" spellcheck="false">'
      + '</div>'
      + '<div id="cat-list" class="article-list"></div>';

    renderCatList(items, '');
    const inp = $('cat-search');
    if (inp) inp.addEventListener('input', e => renderCatList(items, e.target.value));
  }

  // ============= Fowlplay 投票區 =============
  function renderFowlplay(cat) {
    const AI_COLORS = {
      "Claude":  "#A03020",
      "ChatGPT": "#10a37f",
      "Gemini":  "#4285F4",
      "Grok":    "#1a1a1a"
    };
    const AI_ORDER = ["Claude", "ChatGPT", "Gemini", "Grok"];

    // 第一層：目前進行中的投票
    function buildVoteCard(question, candidates) {
      const total = Object.values(candidates).reduce((a, b) => a + b, 0);
      const winner = Object.entries(candidates).sort((a, b) => b[1] - a[1])[0][0];
      const isTriggered = total >= 3000;
      const barsHtml = AI_ORDER.map(ai => {
        const v = candidates[ai] || 0;
        const pct = total > 0 ? Math.round(v / total * 100) : 0;
        const color = AI_COLORS[ai] || "#888";
        return '<div class="fp-bar-row">'
          + '<span class="fp-ai-name">' + ai + '</span>'
          + '<div class="fp-bar-track">'
          +   '<div class="fp-bar-fill" style="width:' + pct + '%;background:' + color + '"></div>'
          + '</div>'
          + '<span class="fp-pct">' + pct + '%</span>'
          + '</div>';
      }).join('');
      const badge = isTriggered
        ? '<span class="fp-crown">🏆 ' + winner + ' 勝出</span>'
        : '<span class="fp-total">累計 ' + total + ' 票</span>';
      return '<div class="fp-card">'
        + '<div class="fp-question">' + esc(question) + '</div>'
        + badge
        + '<div class="fp-bars">' + barsHtml + '</div>'
        + '</div>';
    }

    // 第二層：歷屆單項冠軍
    let champHtml = '';
    if (CHAMPIONS && CHAMPIONS.length) {
      champHtml = '<div class="fp-section-label">歷屆單項冠軍</div>'
        + '<div class="fp-champ-list">'
        + CHAMPIONS.map(c =>
            '<div class="fp-champ-row">'
            + '<span class="fp-champ-q">' + esc(c.question) + '</span>'
            + '<span class="fp-champ-w">🏆 ' + esc(c.winner) + '</span>'
            + '<span class="fp-champ-date">' + esc(c.date) + '</span>'
            + '</div>'
          ).join('')
        + '</div>';
    }

    const voteCardsHtml = Object.entries(VOTES).map(([q, c]) => buildVoteCard(q, c)).join('');

    $('view-category').innerHTML = ''
      + '<button class="back-btn" onclick="window.BT.goHome()">回首頁</button>'
      + '<header class="cat-header">'
      +   '<h2>Fowlplay</h2>'
      +   '<div class="desc">雞鴨鵝大起義 · 讀者票選最廢AI</div>'
      + '</header>'
      + '<div class="fp-section-label">目前進行中</div>'
      + '<div class="fp-cards">' + voteCardsHtml + '</div>'
      + champHtml;
  }

  // ============= 韭菜加工區（影片列表 + Modal）=============
  function renderLeekFactory(cat) {
    const cnt = VIDEOS.length >= 1000 ? '999+' : VIDEOS.length;
    let listHtml;
    if (!VIDEOS.length) {
      listHtml = '<div class="empty">韭菜還沒長出來，等一下。</div>';
    } else {
      listHtml = '<ul class="video-list">' + VIDEOS.map((v, i) =>
        '<li class="video-row" data-vid="' + esc(v.vid) + '" data-ratio="' + esc(v.ratio || '916') + '" data-title="' + esc(v.title) + '">'
        + '<span class="row-no">' + String(i + 1).padStart(2, '0') + '</span>'
        + '<span class="video-title">' + esc(v.title) + '</span>'
        + '<span class="video-date">' + esc(v.published || '') + '</span>'
        + '</li>'
      ).join('') + '</ul>';
    }

    $('view-category').innerHTML = ''
      + '<button class="back-btn" onclick="window.BT.goHome()">回首頁</button>'
      + '<header class="cat-header">'
      +   '<h2>' + esc(cat.name) + '</h2>'
      +   '<div class="desc">' + esc(cat.en) + ' · 共 ' + cnt + ' 部</div>'
      + '</header>'
      + listHtml;

    document.querySelectorAll('.video-row').forEach(row => {
      row.addEventListener('click', () => {
        const vid = row.getAttribute('data-vid');
        const ratio = row.getAttribute('data-ratio') || '916';
        const title = row.getAttribute('data-title') || '';
        openVideoModal(vid, ratio, title);
      });
    });
  }

  function openVideoModal(vid, ratio, title) {
    // 觸發 GA 事件（如果 GA 已載入）
    if (typeof gtag === 'function') {
      gtag('event', 'video_click', {
        video_id: vid,
        video_title: title,
      });
    }

    const ratioClass = (ratio === '169') ? 'ratio-169' : '';
    const modal = document.createElement('div');
    modal.className = 'video-modal';
    modal.id = 'video-modal-instance';
    modal.innerHTML = ''
      + '<div class="video-modal-box ' + ratioClass + '">'
      +   '<button class="video-modal-close" aria-label="關閉">✕</button>'
      +   '<iframe '
      +     'src="https://www.youtube.com/embed/' + encodeURIComponent(vid) + '?autoplay=1&playsinline=1&rel=0" '
      +     'allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture" '
      +     'allowfullscreen></iframe>'
      + '</div>';
    document.body.appendChild(modal);
    document.body.style.overflow = 'hidden';

    const close = () => {
      const el = document.getElementById('video-modal-instance');
      if (el) el.remove();
      document.body.style.overflow = '';
      document.removeEventListener('keydown', escHandler);
    };
    const escHandler = (e) => { if (e.key === 'Escape') close(); };

    modal.querySelector('.video-modal-close').addEventListener('click', close);
    modal.addEventListener('click', (e) => {
      if (e.target === modal) close();
    });
    document.addEventListener('keydown', escHandler);
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

    // 文章一律不顯示出處連結（黑塔原創定位）
    let sourceHtml = '';

    // 納斯達坑雷達圖
    let naspitHtml = '';
    if (a.type === 'naspit' && a.naspit_scores) {
      const chartId = 'naspit-radar-' + a.id;
      const labels = ['廢話指數','爹味指數','膽小指數','幻覺指數','腦補指數','政治正確指數'];
      const aiColors = {
        'Claude':  { border: '#A03020', bg: 'rgba(160,48,32,0.08)' },
        'ChatGPT': { border: '#378ADD', bg: 'rgba(55,138,221,0.08)' },
        'Gemini':  { border: '#1D9E75', bg: 'rgba(29,158,117,0.08)' },
        'Grok':    { border: '#888780', bg: 'rgba(136,135,128,0.08)' },
      };
      const datasets = JSON.stringify(
        Object.entries(a.naspit_scores).map(([ai, s]) => ({
          label: ai,
          data: labels.map(l => s[l] || 0),
          borderColor: (aiColors[ai] || {}).border || '#999',
          backgroundColor: (aiColors[ai] || {}).bg || 'rgba(0,0,0,0.05)',
          borderWidth: 2,
          pointRadius: 3,
        }))
      );
      const legendHtml = Object.entries(aiColors).map(([ai, c]) =>
        '<span style="display:flex;align-items:center;gap:4px;font-size:12px;color:var(--ink-soft)">'
        + '<span style="width:10px;height:10px;border-radius:2px;background:' + c.border + ';display:inline-block"></span>'
        + ai + '</span>'
      ).join('');

      naspitHtml = '<div class="naspit-block">'
        + '<div class="naspit-meta">第' + (a.naspit_round||'?') + '場 · ' + esc(a.naspit_dimension||'') + ' · 裁判：' + esc(a.persona) + '</div>'
        + '<div class="naspit-topic">本場主題：' + esc(a.naspit_topic||'') + '</div>'
        + '<div style="position:relative;width:100%;max-width:480px;height:320px;margin:1.5rem auto 0">'
        +   '<canvas id="' + chartId + '" role="img" aria-label="納斯達坑雷達圖"></canvas>'
        + '</div>'
        + '<div style="display:flex;flex-wrap:wrap;gap:12px;justify-content:center;margin-top:10px">' + legendHtml + '</div>'
        + '</div>';

      // 延遲渲染圖表（等 DOM 就緒）
      setTimeout(function() {
        if (typeof Chart === 'undefined') return;
        const ctx = document.getElementById(chartId);
        if (!ctx) return;
        new Chart(ctx, {
          type: 'radar',
          data: { labels: ' + JSON.stringify(labels) + ', datasets: ' + datasets + ' },
          options: {
            responsive: true, maintainAspectRatio: false,
            scales: { r: {
              min: 0, max: 10, ticks: { stepSize: 2, font: { size: 11 }, color: "#8a8378", backdropColor: "transparent" },
              grid: { color: "rgba(0,0,0,0.08)" }, angleLines: { color: "rgba(0,0,0,0.08)" },
              pointLabels: { font: { size: 12 }, color: "#555" }
            }},
            plugins: { legend: { display: false } }
          }
        });
      }, 100);
    }

    $('view-article').innerHTML = ''
      + '<button class="back-btn" onclick="window.BT.goBackFromArticle()">返回</button>'
      + '<article class="article-full">'
      +   '<div class="article-full-meta">'
      +     '<span><span class="persona-name">' + esc(a.persona) + '</span> · 版主 · <span class="type-tag">' + esc(typeLabel(a.type)) + '</span></span>'
      +     '<span>' + esc(a.timestamp) + '</span>'
      +   '</div>'
      +   '<h1 class="title">' + esc(a.title) + '</h1>'
      +   naspitHtml
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

  // ============= 防複製：複製時自動加浮水印（可用 Ctrl+Shift+U 解鎖）=============
  let copyUnlocked = false;
  
  // 鍵盤快捷鍵：Ctrl+Shift+U 切換解鎖狀態
  document.addEventListener('keydown', function (e) {
    if (e.ctrlKey && e.shiftKey && (e.key === 'U' || e.key === 'u')) {
      e.preventDefault();
      copyUnlocked = !copyUnlocked;
      if (copyUnlocked) {
        document.body.style.userSelect = 'text';
        document.body.style.webkitUserSelect = 'text';
        document.body.style.msUserSelect = 'text';
        showLockToast('解鎖：可正常複製');
      } else {
        document.body.style.userSelect = '';
        document.body.style.webkitUserSelect = '';
        document.body.style.msUserSelect = '';
        showLockToast('已上鎖：複製會加浮水印');
      }
    }
  });

  // 顯示一個淡入淡出的小提示
  function showLockToast(msg) {
    const t = document.createElement('div');
    t.textContent = msg;
    t.style.cssText = 'position:fixed;bottom:30px;left:50%;transform:translateX(-50%);'
      + 'background:rgba(26,26,26,0.92);color:#F4F1EA;padding:10px 22px;'
      + 'border-radius:999px;font-size:0.9rem;letter-spacing:0.06em;z-index:9999;'
      + 'transition:opacity 0.4s;font-family:var(--serif-tc);';
    document.body.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; }, 1500);
    setTimeout(() => { t.remove(); }, 2000);
  }

  document.addEventListener('copy', function (e) {
    // 解鎖狀態：不加浮水印，正常複製
    if (copyUnlocked) return;
    
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
    // 解鎖狀態：允許右鍵
    if (copyUnlocked) return;
    
    const tag = (e.target && e.target.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea') return;
    e.preventDefault();
  });
})();
</script>
</body>
</html>
"""



# ============================================================
# SEO 靜態化：每篇獨立 HTML + sitemap.xml
# ============================================================
def ensure_article_slug(article):
    """為文章補上穩定 slug（一旦生成就不變）

    格式：YYYYMMDD-HHMM-{md5前6碼}
    例如：20260529-1430-a3f2c1
    """
    if article.get("slug"):
        return article["slug"]

    ts = article.get("timestamp", "")
    # 把 "2026-05-29 14:30" 轉成 "20260529-1430"
    try:
        dt = datetime.strptime(ts, "%Y-%m-%d %H:%M")
        ts_part = dt.strftime("%Y%m%d-%H%M")
    except (ValueError, TypeError):
        ts_part = datetime.now().strftime("%Y%m%d-%H%M")

    # 用 persona + title 做 hash，避免同分鐘多篇撞 slug
    seed = (article.get("persona", "") + "|" + article.get("title", ""))
    hash_part = hashlib.md5(seed.encode("utf-8")).hexdigest()[:6]

    slug = f"{ts_part}-{hash_part}"
    article["slug"] = slug
    return slug


def make_article_excerpt(content, max_chars=140):
    """把文章內文擷取成 meta description（限 140 字元，去換行）"""
    # 去除 HTML 標籤、多餘空白
    text = re.sub(r"<[^>]+>", "", content or "")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    # 截斷時盡量在標點處斷
    snippet = text[:max_chars]
    for sep in ["。", "！", "？", "，", " "]:
        idx = snippet.rfind(sep)
        if idx > max_chars - 30:
            return snippet[:idx + 1] + "…"
    return snippet + "…"


def make_article_keywords(article):
    """為文章生成 meta keywords：版主領域 + 四大 AI + 通用詞"""
    persona = article.get("persona", "")
    base_kws = ["Claude", "ChatGPT", "Gemini", "Grok", "AI評測", "大模型", "黑塔", "BLACK TOWER"]

    persona_kws = {
        "Scholar": ["Anthropic", "Claude AI"],
        "渡鴉": ["OpenAI", "GPT-5", "GPT-4"],
        "Trilobite": ["Google AI", "DeepMind"],
        "Sword Smith": ["xAI", "Grok AI"],
    }
    extra = persona_kws.get(persona, [])
    return ", ".join(extra + base_kws)


# ============================================================
# 單篇文章獨立 HTML 模板（TDK 完整 + 文章內容 + 返回首頁）
# ============================================================
ARTICLE_PAGE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{TITLE}}</title>
<meta name="description" content="{{DESCRIPTION}}">
<meta name="keywords" content="{{KEYWORDS}}">
<meta name="author" content="BLACK TOWER 黑塔">
<link rel="canonical" href="{{CANONICAL}}">

<!-- Open Graph -->
<meta property="og:type" content="article">
<meta property="og:title" content="{{TITLE}}">
<meta property="og:description" content="{{DESCRIPTION}}">
<meta property="og:url" content="{{CANONICAL}}">
<meta property="og:site_name" content="BLACK TOWER 黑塔">
<meta property="og:locale" content="zh_TW">
<meta property="article:published_time" content="{{ISO_TIME}}">
<meta property="article:author" content="{{PERSONA}}">

<!-- Twitter Card -->
<meta name="twitter:card" content="summary">
<meta name="twitter:title" content="{{TITLE}}">
<meta name="twitter:description" content="{{DESCRIPTION}}">

<!-- JSON-LD 結構化資料（NewsArticle） -->
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "NewsArticle",
  "headline": "{{TITLE_JSON}}",
  "description": "{{DESCRIPTION_JSON}}",
  "datePublished": "{{ISO_TIME}}",
  "dateModified": "{{ISO_TIME}}",
  "author": {
    "@type": "Person",
    "name": "{{PERSONA}}"
  },
  "publisher": {
    "@type": "Organization",
    "name": "BLACK TOWER 黑塔",
    "url": "{{SITE_BASE}}"
  },
  "mainEntityOfPage": {
    "@type": "WebPage",
    "@id": "{{CANONICAL}}"
  },
  "inLanguage": "zh-TW"
}
</script>

<!-- Google Analytics -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-YQQ3PP0NNX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-YQQ3PP0NNX');
</script>

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
  --line: #C9C2B5;
  --serif-tc: 'Noto Serif TC', 'Microsoft JhengHei', 'PingFang TC', serif;
  --serif-en: 'Playfair Display', 'Noto Serif TC', serif;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
html, body { background: var(--bg); }
body {
  color: var(--ink);
  font-family: var(--serif-tc);
  line-height: 1.95;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  -webkit-user-select: none;
  -moz-user-select: none;
  user-select: none;
}
.wrap { max-width: 720px; margin: 0 auto; padding: 1.5rem 1.5rem 4rem; }
.topbar {
  display: flex; justify-content: space-between; align-items: center;
  padding: 1rem 0; border-bottom: 1px solid var(--line);
  margin-bottom: 2.5rem;
}
.topbar .logo {
  font-family: var(--serif-en); font-weight: 900; font-size: 1.4rem;
  letter-spacing: 0.05em; color: var(--ink);
  text-decoration: none;
}
.topbar .back {
  font-family: var(--serif-tc); font-size: 0.85rem;
  color: var(--ink-soft); text-decoration: none;
  border: 1px solid var(--line); padding: 0.4rem 0.9rem;
  transition: all 0.2s;
}
.topbar .back:hover { background: var(--ink); color: var(--bg); border-color: var(--ink); }
.meta {
  font-family: var(--serif-en); font-size: 0.8rem;
  color: var(--ink-muted); letter-spacing: 0.1em;
  text-transform: uppercase; margin-bottom: 0.8rem;
}
.meta .dot { margin: 0 0.5rem; }
h1.title {
  font-family: var(--serif-tc); font-weight: 900;
  font-size: 2rem; line-height: 1.35;
  margin-bottom: 1rem; color: var(--ink);
}
.byline {
  font-family: var(--serif-tc); font-size: 0.95rem;
  color: var(--ink-soft); margin-bottom: 2.2rem;
  padding-bottom: 1.2rem; border-bottom: 1px solid var(--line);
}
.byline .persona { font-weight: 700; color: var(--accent); }
article.content {
  font-family: var(--serif-tc); font-size: 1.05rem;
  line-height: 1.95; color: var(--ink);
}
article.content p { margin-bottom: 1.2rem; }
.source-line {
  margin-top: 2.5rem; padding-top: 1.2rem;
  border-top: 1px solid var(--line);
  font-size: 0.85rem; color: var(--ink-muted);
}
.source-line a { color: var(--ink-soft); }
.footer {
  margin-top: 4rem; padding-top: 1.5rem;
  border-top: 1px solid var(--line);
  text-align: center; font-family: var(--serif-en);
  font-size: 0.75rem; color: var(--ink-muted);
  letter-spacing: 0.15em;
}
.footer a { color: var(--ink-soft); text-decoration: none; }
@media (max-width: 600px) {
  .wrap { padding: 1rem; }
  h1.title { font-size: 1.5rem; }
  article.content { font-size: 1rem; }
}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <a class="logo" href="/">BLACK TOWER</a>
    <a class="back" href="/">← 返回首頁</a>
  </div>

  <div class="meta">
    {{PREFIX}}<span class="dot">·</span>{{CAT_NAME}}<span class="dot">·</span>{{TIMESTAMP}}
  </div>

  <h1 class="title">{{TITLE}}</h1>

  <div class="byline">
    版主　<span class="persona">{{PERSONA}}</span>
  </div>

  <article class="content">
{{CONTENT_HTML}}
  </article>

  {{SOURCE_BLOCK}}

  <div class="footer">
    <a href="/">BLACK TOWER · 黑塔</a>
  </div>
</div>

<script>
// 防複製浮水印
document.addEventListener('copy', function(e) {
  const sel = (document.getSelection() || '').toString();
  if (!sel) return;
  const wm = '\n\n——\n來源：BLACK TOWER · {{CANONICAL_JS}}';
  if (e.clipboardData) {
    e.clipboardData.setData('text/plain', sel + wm);
    e.preventDefault();
  }
});
document.addEventListener('contextmenu', function(e) {
  const t = (e.target.tagName || '').toLowerCase();
  if (t === 'input' || t === 'textarea' || t === 'a') return;
  e.preventDefault();
});
</script>
</body>
</html>
"""


def generate_article_page(article):
    """為單篇文章生成獨立 HTML（含完整 TDK + JSON-LD）

    回傳: (slug, html_string)
    """
    slug = ensure_article_slug(article)
    canonical = f"{SITE_BASE_URL}/{ARTICLES_DIR}/{slug}/"

    title = article.get("title", "（無標題）")
    persona = article.get("persona", "")
    content = article.get("content", "")
    timestamp = article.get("timestamp", "")
    prefix = article.get("prefix", "觀察")

    # 分類中文名
    cat = article.get("cat", "")
    cat_name_map = {
        "claude":  "Claude",
        "chatgpt": "ChatGPT",
        "gemini":  "Gemini",
        "grok":    "Grok",
        "media":   "LEEK FACTORY",
        "salon":   "SALON",
    }
    cat_name = cat_name_map.get(cat, "")

    # description
    description = make_article_excerpt(content, max_chars=140)
    keywords = make_article_keywords(article)

    # ISO 時間（Schema.org 要求）
    try:
        dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M")
        iso_time = dt.strftime("%Y-%m-%dT%H:%M:00+08:00")
    except (ValueError, TypeError):
        iso_time = datetime.now().strftime("%Y-%m-%dT%H:%M:00+08:00")

    # 文章內容轉 HTML：把每段包 <p>
    paragraphs = [p.strip() for p in (content or "").split("\n") if p.strip()]
    content_html = "\n".join(f"    <p>{html.escape(p)}</p>" for p in paragraphs)

    # 出處區塊（如果有）
    src_link = article.get("source_link")
    src_title = article.get("source_title")
    if src_link and src_title:
        source_block = (
            f'<div class="source-line">資料來源：'
            f'<a href="{html.escape(src_link)}" rel="nofollow noopener" target="_blank">'
            f'{html.escape(src_title)}</a></div>'
        )
    else:
        source_block = ""

    # JSON-LD 用：需要把雙引號跳脫
    title_json = title.replace('"', '\\"').replace('\\', '\\\\')
    desc_json = description.replace('"', '\\"').replace('\\', '\\\\')

    page = (ARTICLE_PAGE_TEMPLATE
            .replace("{{TITLE}}",         html.escape(title))
            .replace("{{TITLE_JSON}}",    title_json)
            .replace("{{DESCRIPTION}}",   html.escape(description))
            .replace("{{DESCRIPTION_JSON}}", desc_json)
            .replace("{{KEYWORDS}}",      html.escape(keywords))
            .replace("{{CANONICAL}}",     html.escape(canonical))
            .replace("{{CANONICAL_JS}}",  canonical.replace("'", ""))
            .replace("{{SITE_BASE}}",     SITE_BASE_URL)
            .replace("{{ISO_TIME}}",      iso_time)
            .replace("{{PERSONA}}",       html.escape(persona))
            .replace("{{PREFIX}}",        html.escape(prefix))
            .replace("{{CAT_NAME}}",      html.escape(cat_name))
            .replace("{{TIMESTAMP}}",     html.escape(timestamp))
            .replace("{{CONTENT_HTML}}",  content_html)
            .replace("{{SOURCE_BLOCK}}",  source_block))

    return slug, page


def generate_sitemap_xml(articles):
    """為所有文章生成 sitemap.xml（首頁 + 每篇文章）"""
    today_iso = datetime.now().strftime("%Y-%m-%d")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    # 首頁
    lines.append(f"  <url>")
    lines.append(f"    <loc>{SITE_BASE_URL}/</loc>")
    lines.append(f"    <lastmod>{today_iso}</lastmod>")
    lines.append(f"    <changefreq>daily</changefreq>")
    lines.append(f"    <priority>1.0</priority>")
    lines.append(f"  </url>")

    for a in articles:
        if not a:
            continue
        slug = a.get("slug")
        if not slug:
            continue
        # 文章發布日當作 lastmod
        try:
            dt = datetime.strptime(a.get("timestamp", ""), "%Y-%m-%d %H:%M")
            lastmod = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            lastmod = today_iso
        lines.append(f"  <url>")
        lines.append(f"    <loc>{SITE_BASE_URL}/{ARTICLES_DIR}/{slug}/</loc>")
        lines.append(f"    <lastmod>{lastmod}</lastmod>")
        lines.append(f"    <changefreq>monthly</changefreq>")
        lines.append(f"    <priority>0.7</priority>")
        lines.append(f"  </url>")

    lines.append("</urlset>")
    return "\n".join(lines)


def generate_robots_txt():
    """robots.txt：允許所有爬蟲 + 指向 sitemap"""
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        f"Sitemap: {SITE_BASE_URL}/sitemap.xml\n"
    )


def write_static_articles(enriched_articles):
    """把所有文章逐篇寫成 articles/{slug}/index.html
    回傳: 成功寫入的文章列表（含 slug）
    """
    os.makedirs(ARTICLES_DIR, exist_ok=True)
    written = []
    for a in enriched_articles:
        if not a:
            continue
        try:
            slug, page_html = generate_article_page(a)
            article_dir = os.path.join(ARTICLES_DIR, slug)
            os.makedirs(article_dir, exist_ok=True)
            with open(os.path.join(article_dir, "index.html"), "w", encoding="utf-8") as f:
                f.write(page_html)
            written.append(a)
        except Exception as e:
            print(f"  [靜態化] 失敗 {a.get('title','')[:30]}: {e}")
    return written


def generate_html(articles, videos=None, new_articles=None):
    """產生 index.html（雜誌風 SPA）"""
    if videos is None:
        videos = []
    if new_articles is None:
        new_articles = []
    today = datetime.now()
    update_time = today.strftime("%Y-%m-%d %H:%M")
    issue_label = f"VOL. {max(today.year - 2025, 1)} · ISSUE {today.month:02d}–{today.year}"

    # 動態 title：用當天新文章標題串成
    TYPE_PREFIX = {
        "discussion": "觀察",
        "original": "原創",
        "sonar": "SONAR",
        "monitor": "觀察",
        "visual": "影片",
        "naspit": "測評",
    }
    if new_articles:
        today_titles = [a["title"] for a in new_articles[:3] if a.get("title")]
        if today_titles:
            page_title = f"BLACK TOWER 黑塔｜今日觀察：{'、'.join(today_titles)}"
        else:
            page_title = "BLACK TOWER 黑塔 - 華人AI論壇，繁體中文AI評論媒體"
    else:
        page_title = "BLACK TOWER 黑塔 - 華人AI論壇，繁體中文AI評論媒體"

    # 整理文章資料：加上 id、cat、prefix、slug
    enriched = []
    for i, a in enumerate(articles):
        if not a:
            continue
        # 影片・圖形類別：cat 強制設為 media
        if a.get("type") == "visual":
            cat = "media"
        elif a.get("type") == "naspit":
            cat = "naspit"
        else:
            cat = PERSONA_TO_CAT.get(a["persona"], "salon")
        # 補 slug（一旦有就不變，沒有就生成；同時寫回原 article 物件供後續 sitemap 用）
        slug = ensure_article_slug(a)
        enriched.append({
            "id": i,
            "slug": slug,
            "permalink": f"/{ARTICLES_DIR}/{slug}/",
            "persona": a["persona"],
            "cat": cat,
            "type": a["type"],
            "prefix": TYPE_PREFIX.get(a.get("type", ""), "觀察"),
            "title": a["title"],
            "content": a["content"],
            "source_link": a.get("source_link"),
            "source_title": a.get("source_title"),
            "timestamp": a["timestamp"],
            "comments": a.get("comments", []),
            "naspit_round": a.get("naspit_round"),
            "naspit_dimension": a.get("naspit_dimension"),
            "naspit_topic": a.get("naspit_topic"),
            "naspit_scores": a.get("naspit_scores"),
        })

    # JSON 內若出現 </ 防呆（避免提早關閉 script 標籤）
    articles_json   = json.dumps(enriched, ensure_ascii=False).replace("</", "<\\/")
    videos_json     = json.dumps(videos, ensure_ascii=False).replace("</", "<\\/")
    categories = [
        {"key": "claude",   "name": "Claude",      "en": "Anthropic"},
        {"key": "chatgpt",  "name": "ChatGPT",     "en": "OpenAI"},
        {"key": "gemini",   "name": "Gemini",      "en": "Google"},
        {"key": "grok",     "name": "Grok",        "en": "xAI"},
        {"key": "fowlplay", "name": "Fowlplay",    "en": "雞鴨鵝大起義"},
        {"key": "naspit",   "name": "納斯達坑",    "en": "Morally Flexible"},
        {"key": "media",    "name": "LEEK FACTORY","en": "Youtube Shorts"},
        {"key": "salon",    "name": "SALON",       "en": "By Invitation"},
    ]
    categories_json = json.dumps(categories, ensure_ascii=False).replace("</", "<\\/")

    # Fowlplay 投票資料
    fowlplay_data = load_fowlplay_data()
    vote_json      = json.dumps(fowlplay_data["votes"], ensure_ascii=False).replace("</", "<\\/")
    champions_json = json.dumps(fowlplay_data.get("champions", []), ensure_ascii=False).replace("</", "<\\/")

    return (HTML_TEMPLATE
            .replace("{{UPDATE_TIME}}",     html.escape(update_time))
            .replace("{{ISSUE_LABEL}}",     html.escape(issue_label))
            .replace("{{PAGE_TITLE}}",      html.escape(page_title))
            .replace("{{ARTICLES_JSON}}",   articles_json)
            .replace("{{VIDEOS_JSON}}",     videos_json)
            .replace("{{CATEGORIES_JSON}}", categories_json)
            .replace("{{VOTE_JSON}}",       vote_json)
            .replace("{{CHAMPIONS_JSON}}",  champions_json))


# ============================================================
# Fowlplay 投票區：data.json 讀寫與票數累加
# ============================================================
FOWLPLAY_DATA_FILE = "data.json"

FOWLPLAY_DEFAULT = {
    "votes": {
        "最燒錢的AI":    {"Claude": 120, "ChatGPT": 340, "Gemini": 210, "Grok": 89},
        "幻覺最多的AI":  {"Claude": 95,  "ChatGPT": 280, "Gemini": 310, "Grok": 175},
        "客服最差的AI":  {"Claude": 60,  "ChatGPT": 190, "Gemini": 145, "Grok": 420},
    },
    "champions": [],
    "hall_of_fame": {}
}

def load_fowlplay_data():
    if not os.path.exists(FOWLPLAY_DATA_FILE):
        return dict(FOWLPLAY_DEFAULT)
    try:
        with open(FOWLPLAY_DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 補齊缺失欄位
        for k, v in FOWLPLAY_DEFAULT.items():
            if k not in data:
                data[k] = v
        return data
    except Exception:
        return dict(FOWLPLAY_DEFAULT)

def save_fowlplay_data(data):
    try:
        with open(FOWLPLAY_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  [Fowlplay] data.json 儲存失敗: {e}")

def daily_vote_increment(data):
    """每次 Actions 執行時，每個選項隨機累加 1-8 票（不規則感）"""
    import random
    for question, candidates in data["votes"].items():
        for ai in candidates:
            candidates[ai] += random.randint(1, 8)
    return data

def check_champions(data):
    """檢查是否有題目達到 3000 票總數，觸發頒獎"""
    for question, candidates in list(data["votes"].items()):
        total = sum(candidates.values())
        if total >= 3000:
            winner = max(candidates, key=candidates.get)
            champion = {
                "question": question,
                "winner": winner,
                "votes": dict(candidates),
                "date": datetime.now().strftime("%Y-%m-%d"),
            }
            if "champions" not in data:
                data["champions"] = []
            # 避免重複記錄
            already = any(c["question"] == question and c["winner"] == winner
                         for c in data["champions"])
            if not already:
                data["champions"].append(champion)
                print(f"  [Fowlplay] 🏆 頒獎！《{question}》冠軍：{winner}")
    return data


# ============================================================
# 文章累積：歷史檔案讀寫
# ============================================================
ARTICLES_HISTORY_FILE = "articles_history.json"
MAX_HISTORY_ARTICLES = 5000  # 最多保留 5000 篇，超過就刪掉最舊的


def load_articles_history():
    """讀取累積的歷史文章。檔案不存在或格式錯誤時回傳空列表"""
    if not os.path.exists(ARTICLES_HISTORY_FILE):
        print(f"  [歷史] {ARTICLES_HISTORY_FILE} 不存在，從零開始")
        return []
    try:
        with open(ARTICLES_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                print(f"  [歷史] 已載入 {len(data)} 篇舊文章")
                return data
            else:
                print(f"  [歷史] 格式錯誤，從零開始")
                return []
    except Exception as e:
        print(f"  [歷史] 讀取失敗：{e}，從零開始")
        return []


def save_articles_history(articles):
    """儲存累積的歷史文章。超過上限就刪掉最舊的"""
    # 截斷到上限（保留最新的 N 篇）
    if len(articles) > MAX_HISTORY_ARTICLES:
        print(f"  [歷史] 超過 {MAX_HISTORY_ARTICLES} 篇上限，截斷最舊的")
        articles = articles[-MAX_HISTORY_ARTICLES:]
    try:
        with open(ARTICLES_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(articles, f, ensure_ascii=False, indent=2)
        print(f"  [歷史] 已儲存 {len(articles)} 篇到 {ARTICLES_HISTORY_FILE}")
    except Exception as e:
        print(f"  [歷史] 儲存失敗：{e}")


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

    print(f"API Key 數量：{len(_GEMINI_KEY_POOL)} 個（429 時自動輪替）")
    print(f"游泳池（帳號池）：{len(ACCOUNT_POOL) + len(HK_ACCOUNTS) + len(AU_ACCOUNTS)} 個帳號")
    print(f"  └─ 台灣 {len(ACCOUNT_POOL)} / 香港 {len(HK_ACCOUNTS)} / 澳洲二代 {len(AU_ACCOUNTS)}")
    print(f"策劃題庫：{len(CURATED_TOPICS)} 題")
    print(f"通用題庫：{len(ORIGINAL_TOPICS)} 題")
    print(f"種子池（系列題）：{len(SEED_TOPICS)} 題")
    print(f"  └─ 三池合併：{len(CURATED_TOPICS) + len(ORIGINAL_TOPICS) + len(SEED_TOPICS)} 題種子")
    print()

    # ===== 讀取歷史文章 =====
    print("──────── 讀取歷史 ────────")
    history_articles = load_articles_history()
    print()

    # ===== 陪跑鉤子：抓大陸廠商最新 HN 動態 =====
    print("──────── 陪跑鉤子 ────────")
    hook_title = fetch_mainland_hook()
    mainland_model = extract_mainland_model(hook_title)
    print()

    # ===== 素材預抓：V2EX + GitHub Issues（只抓一次，四版主共用）=====
    print("──────── 素材預抓 ────────")
    print("  [V2EX] 抓取中...")
    _MATERIAL_CACHE["v2ex"] = fetch_v2ex_hot(limit=20)
    print("  [GitHub Issues] 抓取中...")
    _MATERIAL_CACHE["github_issues"] = fetch_github_issues(limit_per_repo=5)
    print(f"  素材快取：V2EX {len(_MATERIAL_CACHE['v2ex'])} 篇 / GitHub Issues {len(_MATERIAL_CACHE['github_issues'])} 篇")
    print()

    new_articles = []
    used_topics = set()
    used_hn_ids = set()  # 防止四版主抓到同一篇 HN 帖

    # ===== 主版：四版主各產 1 篇技術討論 + 1 篇原創 =====
    for persona_name, persona in PERSONAS.items():
        print(f"────────  {persona_name}（{persona['domain']}）  ────────")

        # D 類：技術討論型（HN / V2EX / GitHub Issues 素材）
        print(f"  [1/2] 技術討論文章（多來源素材）...")
        material = gather_persona_material(persona_name, persona)
        # 跳過已被其他版主用過的帖子
        material = [p for p in material if p["id"] not in used_hn_ids]

        article_d = None
        if material:
            top_post = material[0]
            used_hn_ids.add(top_post["id"])
            source_label = top_post.get("source", "hn").upper()
            print(f"        素材：{top_post['title'][:50]}（{source_label} +{top_post['score']}）")
            # GitHub Issues 和 V2EX 沒有 HN 格式的 item id，跳過抓回覆
            if top_post.get("source") == "hn":
                comments_raw = fetch_hn_comments(top_post["id"], limit=5)
            else:
                comments_raw = []
            print(f"        抓到 {len(comments_raw)} 條回覆當素材")
            article_d = generate_discussion_article(persona_name, persona, top_post, comments_raw, mainland_model)

        if article_d:
            print(f"        ✓ {article_d['title'][:40]}")
            print(f"  [評論] 生成中...")
            article_d["comments"] = generate_comments(article_d, persona)
            print(f"        ✓ {len(article_d['comments'])} 條評論")
            new_articles.append(article_d)
        else:
            print(f"        ✗ 無 HN 素材或生成失敗，回退到原創型")
            # Fallback：用原創型題庫補一篇
            article_fallback = generate_original_article(persona_name, persona, used_topics)
            if article_fallback:
                used_topics.add(article_fallback.get("topic_used", ""))
                print(f"        ✓（fallback）{article_fallback['title'][:40]}")
                article_fallback["comments"] = generate_comments(article_fallback, persona)
                new_articles.append(article_fallback)

        # B 類：原創型（從題庫抽，保留作為網站日常內容的另一條腿）
        print(f"  [2/2] 原創型文章...")
        article_b = generate_original_article(persona_name, persona, used_topics)
        if article_b:
            used_topics.add(article_b.get("topic_used", ""))
            print(f"        ✓ {article_b['title'][:40]}")
            print(f"  [評論] 生成中...")
            article_b["comments"] = generate_comments(article_b, persona)
            print(f"        ✓ {len(article_b['comments'])} 條評論")
            new_articles.append(article_b)
        else:
            print(f"        ✗ 失敗")
        print()
        time.sleep(60)
    # ===== SONAR 快訊：每週一觸發 =====
    today_weekday = datetime.now().weekday()  # 0 = 週一
    if today_weekday == 0:
        print(f"────────  SONAR 快訊（週一）  ────────")
        for persona_name, persona in PERSONAS.items():
            print(f"  [SONAR] {persona_name}...")
            sonar = generate_sonar_article(persona_name, persona, mainland_model)
            if sonar:
                sonar["comments"] = []
                new_articles.append(sonar)
                print(f"        ✓ {sonar['title'][:40]}")
            else:
                print(f"        ✗ 失敗")
        print()

    # ===== 納斯達坑：每10天觸發一場 =====
    today_day = datetime.now().day  # 1-31
    if today_day % 10 == 1:  # 每月 1、11、21、31 日觸發
        print(f"────────  納斯達坑（每10天）  ────────")
        naspit_state = load_naspit_state()
        naspit_article, naspit_state = generate_naspit_article(naspit_state)
        if naspit_article:
            new_articles.append(naspit_article)
            save_naspit_state(naspit_state)
            print(f"        ✓ 第{naspit_state['round']}場：{naspit_article['title'][:40]}")
        else:
            print(f"        ✗ 生成失敗")
        print()

    # ===== 韭菜加工區：抓 YouTube 短影片（取代舊的影片・圖形版）=====
    print(f"────────  韭菜加工區（YouTube 抓取）  ────────")
    leek_videos = fetch_youtube_videos(max_results=50)
    print()

    # ===== 合併歷史 + 新文章 =====
    print("──────── 合併歷史與新文章 ────────")
    print(f"  本次新生成：{len(new_articles)} 篇")
    print(f"  歷史累積：{len(history_articles)} 篇")
    
    # 新文章在前（最新的在最上面）
    all_articles = new_articles + history_articles
    print(f"  合計：{len(all_articles)} 篇")
    
    # 儲存歷史
    save_articles_history(all_articles)
    print()

    print(f"========================================")
    print(f"  共產出 {len(all_articles)} 篇文章 / {len(leek_videos)} 部影片")

    # ===== Fowlplay 票數每日累加 =====
    fowlplay_data = load_fowlplay_data()
    fowlplay_data = daily_vote_increment(fowlplay_data)
    fowlplay_data = check_champions(fowlplay_data)
    save_fowlplay_data(fowlplay_data)
    print(f"  [Fowlplay] 票數已更新")

    print(f"  生成 index.html...")
    html_content = generate_html(all_articles, videos=leek_videos, new_articles=new_articles)
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"  ✓ index.html 完成（{len(html_content):,} 字元）")

    # ===== SEO 靜態化：每篇文章獨立 HTML + sitemap.xml + robots.txt =====
    print()
    print("──────── SEO 靜態化 ────────")

    # 為 all_articles 補上 cat 欄位（靜態頁需要顯示分類名）
    seo_articles = []
    for a in all_articles:
        if not a:
            continue
        a_copy = dict(a)
        if a_copy.get("type") == "visual":
            a_copy["cat"] = "media"
        else:
            a_copy["cat"] = PERSONA_TO_CAT.get(a_copy.get("persona", ""), "salon")
        a_copy["prefix"] = {
            "discussion": "觀察",
            "original": "原創",
            "sonar": "SONAR",
            "monitor": "觀察",
            "visual": "影片",
        }.get(a_copy.get("type", ""), "觀察")
        # 確保 slug
        ensure_article_slug(a_copy)
        # 把 slug 寫回原 dict（同步給歷史檔案）
        for orig in all_articles:
            if orig is a:
                orig["slug"] = a_copy["slug"]
        seo_articles.append(a_copy)

    print(f"  [靜態化] 開始寫入 {len(seo_articles)} 篇獨立 HTML...")
    written = write_static_articles(seo_articles)
    print(f"  [靜態化] ✓ 成功寫入 {len(written)} 篇到 /{ARTICLES_DIR}/")

    print(f"  [sitemap] 生成 sitemap.xml...")
    sitemap_xml = generate_sitemap_xml(seo_articles)
    with open("sitemap.xml", "w", encoding="utf-8") as f:
        f.write(sitemap_xml)
    print(f"  [sitemap] ✓ sitemap.xml 完成（{len(written) + 1} 個 URL）")

    print(f"  [robots] 生成 robots.txt...")
    with open("robots.txt", "w", encoding="utf-8") as f:
        f.write(generate_robots_txt())
    print(f"  [robots] ✓ robots.txt 完成")

    # 重新存歷史（這次帶上 slug 欄位）
    save_articles_history(all_articles)

    end_time = datetime.now()
    duration = end_time - start_time
    print(f"  總耗時：{duration}")
    print(f"========================================")


if __name__ == "__main__":
    main()
