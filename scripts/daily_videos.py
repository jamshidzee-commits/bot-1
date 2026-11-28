"""Kuniga 3 ta video: skillar, gollar, futbol memlari.
Videolar YouTube'dan HAVOLA sifatida joylanadi (Telegramning o'zida o'ynaydi) — fayl yuklab olinmaydi va qayta yuklanmaydi,
shuning uchun mualliflik huquqi buzilmaydi va video egasining kanaliga ko'rishlar boradi."""
import os, re, json, html, requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BOT = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
YT_KEY = os.environ["YOUTUBE_API_KEY"]
TG = f"https://api.telegram.org/bot{BOT}/"
TASHKENT = ZoneInfo("Asia/Tashkent")
STATE = "daily_videos.json"

# (kalit, Toshkent vaqti, sarlavha, qidiruv so'rovlari — kun bo'yicha aylanadi, necha kunlik, minimal ko'rishlar)
SLOTS = [
    ("skills", "11:00", "🔥 Kun skili", [
        "Messi skills", "Cristiano Ronaldo skills", "Neymar skills", "Lamine Yamal skills", "Mbappe skills",
        "Vinicius Junior skills", "Ronaldinho skills", "Zidane skills", "Haaland skills", "Salah skills",
        "Maradona skills", "Kvaratskhelia skills", "Bellingham skills", "best football skills dribbling"], 0, 20000),
    ("goals", "16:00", "⚽ Kun goli", [
        "best goals of the week football", "most beautiful goals football", "top goals this week",
        "amazing goals compilation football"], 10, 30000),
    ("memes", "20:30", "😂 Futbol memlari", [
        "football memes", "funny football moments", "futbol memlari", "футбольные приколы", "football funny fails"], 30, 10000),
]
BLOCK = ("bet", "1xbet", "casino", "promo code", "promocode", "18+", "nsfw", "sex", "gambling", "stavka", "ставк", "казино", "fifa 2",
         "efootball", "pes ", "gameplay")
MAX_SECONDS = 300
MAX_TRIES = 12

def load():
    try:
        return json.load(open(STATE, encoding="utf-8"))
    except Exception:
        return {"done": {}, "posted": [], "tries": {}}

def save(s):
    s["posted"] = s["posted"][-600:]
    s["done"] = dict(list(s["done"].items())[-60:])
    s["tries"] = dict(list(s["tries"].items())[-60:])
    json.dump(s, open(STATE, "w", encoding="utf-8"), ensure_ascii=False)

def tg(method, **data):
    try:
        r = requests.post(TG + method, json=data, timeout=30)
        print(method, r.status_code, r.text[:150])
        return r.json()
    except Exception as e:
        print("TG ERROR", method, e)
        return {}

def seconds(iso):
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 10**9
    h, mi, se = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + se

def candidates(query, days):
    params = {"key": YT_KEY, "part": "snippet", "q": query, "type": "video", "maxResults": 25, "videoEmbeddable": "true",
              "videoDuration": "short", "safeSearch": "strict", "order": "viewCount" if days else "relevance"}
    if days:
        params["publishedAfter"] = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = requests.get("https://www.googleapis.com/youtube/v3/search", params=params, timeout=30).json()
    ids = [i["id"]["videoId"] for i in r.get("items", []) if i.get("id", {}).get("videoId")]
    if not ids:
        print("YOUTUBE search bo'sh:", str(r)[:200])
        return []
    v = requests.get("https://www.googleapis.com/youtube/v3/videos", timeout=30,
                     params={"key": YT_KEY, "part": "snippet,contentDetails,statistics,status", "id": ",".join(ids)}).json()
    return v.get("items", [])

def pick(kind, queries, days, min_views, s):
    day = datetime.now(TASHKENT).toordinal()
    q = queries[day % len(queries)]
    for item in candidates(q, days):
        vid, sn = item["id"], item["snippet"]
        title = sn.get("title", "")
        blob = (title + " " + sn.get("channelTitle", "")).lower()
        if vid in s["posted"] or any(b in blob for b in BLOCK):
            continue
        if not item.get("status", {}).get("embeddable", False) or item.get("status", {}).get("madeForKids"):
            continue
        if seconds(item["contentDetails"].get("duration")) > MAX_SECONDS:
            continue
        if int(item.get("statistics", {}).get("viewCount", 0)) < min_views:
            continue
        if sn.get("liveBroadcastContent") not in (None, "none"):
            continue
        return vid, title, sn.get("channelTitle", "")
    return None

def footer():
    try:
        from post_results import channel_info
        link, _ = channel_info()
    except Exception as e:
        print("CHANNEL INFO xato:", e)
        link = ""
    return f'👉 <a href="{html.escape(link)}">FUTBOL OLAMI</a> 👈' if link else "<b>FUTBOL OLAMI</b>"

def post(label, vid, title, channel):
    url = f"https://www.youtube.com/watch?v={vid}"
    text = (f"<b>{label}</b>\n\n▶️ {html.escape(title, quote=False)}\n"
            f"📺 {html.escape(channel, quote=False)}\n\n{footer()}")
    r = tg("sendMessage", chat_id=CHANNEL_ID, text=text, parse_mode="HTML",
           link_preview_options={"url": url, "prefer_small_media": True, "show_above_text": True})
    return bool(r.get("ok"))

def main():
    s = load()
    now = datetime.now(TASHKENT)
    today = now.strftime("%Y-%m-%d")
    for kind, hhmm, label, queries, days, min_views in SLOTS:
        key = f"{today}:{kind}"
        if s["done"].get(key) or now.strftime("%H:%M") < hhmm or s["tries"].get(key, 0) >= MAX_TRIES:
            continue
        s["tries"][key] = s["tries"].get(key, 0) + 1
        try:
            found = pick(kind, queries, days, min_views, s)
        except Exception as e:
            print("YOUTUBE xato:", e)
            found = None
        if not found:
            print(f"{kind}: mos video topilmadi (urinish {s['tries'][key]})")
            continue
        vid, title, channel = found
        if post(label, vid, title, channel):
            s["done"][key] = vid
            s["posted"].append(vid)
    save(s)

if __name__ == "__main__":
    main()
