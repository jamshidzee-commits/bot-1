import os
import json
import html
import requests
from io import BytesIO
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHANNEL_ID = os.environ["CHANNEL_ID"]
TEST_MODE = os.environ.get("TEST_MODE", "false") == "true"
GROUP_ID = os.environ.get("GROUP_ID", "").strip()  # masalan @uzb_fut_fan_club

TASHKENT = ZoneInfo("Asia/Tashkent")
ESPN = "https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/scoreboard"
SENT_FILE = "sent.json"
W = 1080

HERE = os.path.dirname(os.path.abspath(__file__))
REGULAR = os.path.join(HERE, "..", "api", "fonts", "DejaVuSans.ttf")
BOLD = os.path.join(HERE, "..", "api", "fonts", "DejaVuSans-Bold.ttf")

LEAGUES = {
    "eng.1": "ANGLIYA — PREMIER LIGA",
    "esp.1": "ISPANIYA — LA LIGA",
    "ita.1": "ITALIYA — SERIYA A",
    "ger.1": "GERMANIYA — BUNDESLIGA",
    "fra.1": "FRANSIYA — LIGUE 1",
    "por.1": "PORTUGALIYA — PRIMEYRA LIGA",
    "ned.1": "NIDERLANDIYA — EREDIVIZI",
    "tur.1": "TURKIYA — SUPER LIG",
    "ksa.1": "SAUDIYA ARABISTONI — PRO LIGA",
    "uefa.champions": "UEFA — CHEMPIONLAR LIGASI",
    "uefa.europa": "UEFA — YEVROPA LIGASI",
    "uefa.europa.conf": "UEFA — KONFERENSIYALAR LIGASI",
}

MONTHS = {1: "YANVAR", 2: "FEVRAL", 3: "MART", 4: "APREL", 5: "MAY", 6: "IYUN",
          7: "IYUL", 8: "AVGUST", 9: "SENTABR", 10: "OKTABR", 11: "NOYABR", 12: "DEKABR"}
DAYS = {0: "DUSHANBA", 1: "SESHANBA", 2: "CHORSHANBA", 3: "PAYSHANBA",
        4: "JUMA", 5: "SHANBA", 6: "YAKSHANBA"}

SHORT = {
    "Manchester United": "Man United", "Manchester City": "Man City",
    "Tottenham Hotspur": "Tottenham", "Wolverhampton Wanderers": "Wolves",
    "Newcastle United": "Newcastle", "West Ham United": "West Ham",
    "Nottingham Forest": "Nott'm Forest", "Paris Saint-Germain": "PSG",
    "Bayern Munich": "Bayern", "Athletic Club": "Athletic",
    "Borussia Mönchengladbach": "Gladbach", "Borussia Dortmund": "Dortmund",
    "Bayer Leverkusen": "Leverkusen", "Eintracht Frankfurt": "Frankfurt",
    "Atlético Madrid": "Atlético", "Brighton & Hove Albion": "Brighton",
    "AFC Bournemouth": "Bournemouth",
}

logo_cache = {}


def F(size, bold=False):
    return ImageFont.truetype(BOLD if bold else REGULAR, size)


def load_sent():
    try:
        with open(SENT_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_sent(sent):
    with open(SENT_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(sent)[-3000:], f)


def get_events(code, date_string):
    try:
        r = requests.get(
            ESPN.format(code=code),
            params={"dates": date_string.replace("-", ""), "limit": 100},
            timeout=30,
        )
        r.raise_for_status()
        events = r.json().get("events", [])
        print("ESPN", code, date_string, "events:", len(events))
        return events
    except Exception as e:
        print("ESPN ERROR", code, date_string, e)
        return []


def parse_event(ev, upcoming=False):
    comp = ev["competitions"][0]
    status = comp["status"]["type"]
    if upcoming:
        # Только матчи, которые ещё не начались
        if status.get("state") != "pre":
            return None
    elif not status.get("completed"):
        return None
    teams = {c["homeAway"]: c for c in comp["competitors"]}
    home, away = teams["home"], teams["away"]
    dt = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(TASHKENT)
    return {
        "id": ev["id"],
        "dt": dt,
        "home": home["team"]["displayName"],
        "away": away["team"]["displayName"],
        "home_logo": home["team"].get("logo"),
        "away_logo": away["team"].get("logo"),
        "hg": int(float(home.get("score", 0) or 0)),
        "ag": int(float(away.get("score", 0) or 0)),
        "note": {"STATUS_FINAL_AET": "QO'SHIMCHA VAQT",
                 "STATUS_FINAL_PEN": "PENALTILAR"}.get(status.get("name"), ""),
        "upcoming": upcoming,
    }


def get_logo(url):
    if not url:
        return None
    if url in logo_cache:
        return logo_cache[url]
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGBA")
        img.thumbnail((80, 80), Image.Resampling.LANCZOS)
        logo_cache[url] = img
        return img
    except Exception as e:
        print("LOGO ERROR:", e)
        logo_cache[url] = None
        return None


def draw_logo(img, url, cx, cy, size=64):
    d = ImageDraw.Draw(img, "RGBA")
    d.ellipse((cx - size // 2, cy - size // 2, cx + size // 2, cy + size // 2),
              fill=(7, 30, 47, 255), outline=(48, 145, 200, 220), width=2)
    logo = get_logo(url)
    if logo:
        p = logo.copy()
        p.thumbnail((size - 10, size - 10), Image.Resampling.LANCZOS)
        img.alpha_composite(p, (int(cx - p.width / 2), int(cy - p.height / 2)))


def fit_text(d, text, max_width, start=31, minimum=20):
    text = SHORT.get(text, text)
    for size in range(start, minimum - 1, -1):
        f = F(size, True)
        box = d.textbbox((0, 0), text, font=f)
        if box[2] - box[0] <= max_width:
            return text, f
    f = F(minimum, True)
    t = text
    while len(t) > 3:
        cand = t[:-1] + "..."
        box = d.textbbox((0, 0), cand, font=f)
        if box[2] - box[0] <= max_width:
            return cand, f
        t = t[:-1]
    return t, f


LEAGUE_CODE = {name: code for code, name in LEAGUES.items()}

# (fon rangi, chiziq rangi) — har bir davlat uchun o'z tusi
LEAGUE_STYLE = {
    "eng.1": ((48, 20, 72), (160, 100, 220)),
    "esp.1": ((70, 18, 26), (230, 75, 80)),
    "ita.1": ((14, 60, 36), (60, 195, 115)),
    "ger.1": ((58, 48, 8), (230, 190, 40)),
    "fra.1": ((12, 38, 88), (75, 135, 235)),
    "por.1": ((12, 58, 64), (50, 195, 205)),
    "ned.1": ((74, 40, 8), (250, 145, 40)),
    "tur.1": ((82, 12, 24), (240, 65, 75)),
    "ksa.1": ((14, 72, 52), (55, 205, 145)),
}
DEFAULT_STYLE = ((20, 32, 100), (115, 145, 255))

FLAG_W, FLAG_H = 60, 40


def _star(cx, cy, r, points=5):
    import math
    pts = []
    for i in range(points * 2):
        ang = -math.pi / 2 + i * math.pi / points
        rr = r if i % 2 == 0 else r * 0.4
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    return pts


def make_flag(code):
    """Davlat bayrog'ini kod bilan chizadi (tashqi rasm kerak emas)."""
    import math
    k = 4
    w, h = FLAG_W * k, FLAG_H * k
    fl = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    d = ImageDraw.Draw(fl)

    def vert(cols, parts=None):
        parts = parts or [1] * len(cols)
        x, tot = 0, sum(parts)
        for c, pt in zip(cols, parts):
            nx = x + w * pt / tot
            d.rectangle((round(x), 0, round(nx), h), fill=c)
            x = nx

    def horiz(cols, parts=None):
        parts = parts or [1] * len(cols)
        y, tot = 0, sum(parts)
        for c, pt in zip(cols, parts):
            ny = y + h * pt / tot
            d.rectangle((0, round(y), w, round(ny)), fill=c)
            y = ny

    if code == "fra.1":
        vert([(0, 85, 164), (255, 255, 255), (239, 65, 53)])
    elif code == "ita.1":
        vert([(0, 146, 70), (255, 255, 255), (206, 43, 55)])
    elif code == "ger.1":
        horiz([(0, 0, 0), (221, 0, 0), (255, 206, 0)])
    elif code == "ned.1":
        horiz([(174, 28, 40), (255, 255, 255), (33, 71, 139)])
    elif code == "esp.1":
        horiz([(170, 21, 27), (241, 191, 0), (170, 21, 27)], [1, 2, 1])
    elif code == "por.1":
        vert([(0, 102, 0), (255, 0, 0)], [2, 3])
        cx, cy, r = w * 0.4, h / 2, h * 0.2
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 205, 0), outline=(255, 255, 255), width=k)
    elif code == "tur.1":
        d.rectangle((0, 0, w, h), fill=(227, 10, 23))
        r1, r2 = h * 0.27, h * 0.21
        d.ellipse((w * 0.36 - r1, h / 2 - r1, w * 0.36 + r1, h / 2 + r1), fill=(255, 255, 255))
        d.ellipse((w * 0.42 - r2, h / 2 - r2, w * 0.42 + r2, h / 2 + r2), fill=(227, 10, 23))
        d.polygon(_star(w * 0.58, h / 2, h * 0.11), fill=(255, 255, 255))
    elif code == "ksa.1":
        d.rectangle((0, 0, w, h), fill=(0, 106, 78))
        d.rectangle((w * 0.2, h * 0.62, w * 0.8, h * 0.68), fill=(255, 255, 255))
        d.rectangle((w * 0.3, h * 0.3, w * 0.7, h * 0.38), fill=(255, 255, 255))
    elif code == "eng.1":
        d.rectangle((0, 0, w, h), fill=(255, 255, 255))
        d.rectangle((w * 0.42, 0, w * 0.58, h), fill=(206, 17, 36))
        d.rectangle((0, h * 0.4, w, h * 0.6), fill=(206, 17, 36))
    else:  # UEFA va boshqalar: ko'k fon, yulduzlar halqasi
        d.rectangle((0, 0, w, h), fill=(0, 51, 153))
        for i in range(12):
            a = i * math.pi / 6
            cx, cy = w / 2 + h * 0.32 * math.cos(a), h / 2 + h * 0.32 * math.sin(a)
            d.ellipse((cx - 2 * k, cy - 2 * k, cx + 2 * k, cy + 2 * k), fill=(255, 215, 0))

    fl = fl.resize((FLAG_W, FLAG_H), Image.Resampling.LANCZOS)
    mask = Image.new("L", (FLAG_W * k, FLAG_H * k), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, FLAG_W * k - 1, FLAG_H * k - 1), 8 * k, fill=255)
    mask = mask.resize((FLAG_W, FLAG_H), Image.Resampling.LANCZOS)
    fl.putalpha(mask)
    return fl


PRIORITY = ["uefa.champions", "eng.1", "esp.1", "ita.1", "ger.1", "fra.1",
            "uefa.europa", "uefa.europa.conf", "ksa.1", "tur.1", "por.1", "ned.1"]
MAX_ROWS = 24  # bitta rasmga sig'adigan maksimal o'yinlar soni

_channel = {}


def channel_info():
    """(havola, @nom) — kanal havolasi. CHANNEL_LINK env, @username yoki getChat orqali."""
    if _channel:
        return _channel["v"]
    link, handle = os.environ.get("CHANNEL_LINK", "").strip(), ""
    uname = CHANNEL_ID.lstrip("@") if CHANNEL_ID.startswith("@") else ""
    if not link and not uname:
        try:
            r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getChat",
                             params={"chat_id": CHANNEL_ID}, timeout=15).json()
            res = r.get("result", {}) if r.get("ok") else {}
            uname = res.get("username", "")
            link = link or res.get("invite_link", "")
        except Exception as e:
            print("getChat ERROR:", e)
    if uname:
        link = link or f"https://t.me/{uname}"
        handle = "@" + uname
    elif link.startswith("https://t.me/") and "+" not in link and "joinchat" not in link:
        handle = "@" + link.rsplit("/", 1)[-1]
    _channel["v"] = (link, handle)
    return _channel["v"]


def select_main(items, cap=MAX_ROWS):
    """Eng muhim ligalar birinchi; ko'rsatishda vaqt bo'yicha tartiblanadi."""
    rank = {c: i for i, c in enumerate(PRIORITY)}
    chosen = sorted(items, key=lambda x: (rank.get(LEAGUE_CODE.get(x[0]), 99), x[1]["dt"]))[:cap]
    return sorted(chosen, key=lambda x: x[1]["dt"])


def chunk_even(items, size=MAX_ROWS):
    n = max(1, -(-len(items) // size))
    per = -(-len(items) // n)
    return [items[i:i + per] for i in range(0, len(items), per)]


def draw_row(img, y, league, m):
    d = ImageDraw.Draw(img, "RGBA")
    code = LEAGUE_CODE.get(league)
    bg, line = LEAGUE_STYLE.get(code, DEFAULT_STYLE)
    cy = y + 48
    fill = tuple(int(c * 0.55 + 6 * 0.45) for c in bg)
    d.rounded_rectangle((45, y, W - 45, y + 96), 18, fill=fill + (250,), outline=line + (235,), width=2)
    fl = make_flag(code).resize((46, 31), Image.Resampling.LANCZOS)
    img.alpha_composite(fl, (62, cy - 15))

    hn, hf = fit_text(d, m["home"], 262)
    an, af = fit_text(d, m["away"], 320)
    d.text((384, cy), hn, font=hf, fill=(248, 251, 255, 255), anchor="rm")
    draw_logo(img, m["home_logo"], 428, cy, 66)
    draw_logo(img, m["away_logo"], 652, cy, 66)
    d.text((694, cy), an, font=af, fill=(248, 251, 255, 255), anchor="lm")

    d.rounded_rectangle((476, y + 14, 604, y + 80), 14, fill=(8, 58, 84, 255),
                        outline=(55, 160, 215, 230), width=2)
    center = m["dt"].strftime("%H:%M") if m.get("upcoming") else f"{m['hg']} : {m['ag']}"
    d.text((540, y + 47), center, font=F(30, True), fill=(255, 255, 255, 255), anchor="mm")
    if m.get("note"):
        d.text((540, y + 88), m["note"], font=F(15, True), fill=(130, 205, 245, 255), anchor="mm")


def make_list_image(title, dt, rows, page_no=1, total_pages=1):
    """Barcha o'yinlar bitta rasmda: ixcham ro'yxat, pastda kanal nomi."""
    top, step, foot_h = 355, 108, 190
    height = top + len(rows) * step + foot_h
    img = Image.new("RGBA", (W, height), (5, 16, 29, 255))
    d = ImageDraw.Draw(img, "RGBA")

    for yy in range(height):
        ratio = yy / max(1, height - 1)
        d.line((0, yy, W, yy), fill=(int(5 + 3 * ratio), int(17 + 10 * ratio), int(30 + 18 * ratio), 255))
    for x in range(-250, W + 400, 190):
        d.polygon([(x, 0), (x + 65, 0), (x - 170, 250), (x - 235, 250)], fill=(25, 125, 190, 30))

    d.ellipse((55, 42, 155, 142), fill=(10, 72, 112, 110), outline=(70, 185, 240, 230), width=3)
    d.text((82, 59), "F", font=F(50, True), fill=(255, 255, 255, 255))
    d.text((185, 55), "FUTBOL OLAMI", font=F(48, True), fill=(245, 250, 255, 255))
    d.text((188, 112), "Futbol haqida hammasi!", font=F(26), fill=(130, 205, 245, 255))

    d.rounded_rectangle((55, 180, 205, 320), 20, fill=(245, 249, 252, 255))
    d.rounded_rectangle((55, 180, 205, 224), 20, fill=(235, 55, 55, 255))
    d.rectangle((55, 205, 205, 224), fill=(235, 55, 55, 255))
    d.text((130, 203), MONTHS[dt.month], font=F(21, True), fill=(255, 255, 255, 255), anchor="mm")
    d.text((88, 228), dt.strftime("%d"), font=F(58, True), fill=(8, 25, 40, 255))
    d.text((245, 184), title, font=F(40, True), fill=(248, 252, 255, 255))
    d.text((248, 250), f"{dt.strftime('%d.%m.%Y')} | {DAYS[dt.weekday()]}", font=F(25), fill=(145, 200, 230, 255))
    if total_pages > 1:
        d.rounded_rectangle((900, 188, 1018, 242), 16, fill=(7, 105, 155, 235))
        d.text((959, 215), f"{page_no}/{total_pages}", font=F(26, True), fill=(255, 255, 255, 255), anchor="mm")

    y = top
    for league, m in rows:
        draw_row(img, y, league, m)
        y += step

    fy = height - foot_h + 20
    d.line((60, fy, W - 60, fy), fill=(55, 135, 175, 150), width=2)
    _, handle = channel_info()
    d.text((70, fy + 30), "Futbol bizni birlashtiradi!", font=F(33, True), fill=(238, 248, 255, 255))
    tag = f"Telegram: {handle}" if handle else "Futbol olami  •  Futbol haqida hammasi!"
    d.text((70, fy + 88), tag, font=F(32, True), fill=(95, 200, 255, 255))
    return img.convert("RGB")


def _send_photo_to(chat_id, data_bytes, caption):
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
        files={"photo": ("futbol-olami.jpg", BytesIO(data_bytes), "image/jpeg")},
        timeout=30,
    )
    print("TELEGRAM", chat_id, ":", r.status_code, r.text[:200])
    return r.ok


def send_photo(img, caption):
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92, optimize=True)
    data_bytes = buf.getvalue()
    ok = _send_photo_to(CHANNEL_ID, data_bytes, caption)
    if ok and GROUP_ID:
        _send_photo_to(GROUP_ID, data_bytes, caption)
    return ok


def post(items, title, caption_text, dt=None):
    """Bitta ixcham rasm (juda ko'p bo'lsa teng bo'lib bir necha rasm) + kanalga havola."""
    if not items:
        return []
    items = sorted(items, key=lambda x: x[1]["dt"])
    pages = chunk_even(items)
    link, _ = channel_info()
    ok_ids = []
    for no, rows in enumerate(pages, 1):
        img = make_list_image(title, dt or rows[0][1]["dt"], rows, no, len(pages))
        caption = caption_text
        if link:
            caption += f'\n\n<a href="{html.escape(link)}">FUTBOL OLAMI</a> ✈️'
        else:
            caption += "\n\n<b>FUTBOL OLAMI</b>"
        if send_photo(img, caption):
            ok_ids += [m["id"] for _, m in rows]
    return ok_ids


def post_finished(now, sent):
    """Итоги матчей за вчера и сегодня — только те, что ещё не отправлены."""
    days_back = 7 if TEST_MODE else 1
    dates = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_back, -1, -1)]

    finished, seen = [], set()
    for code, label in LEAGUES.items():
        for d in dates:
            for ev in get_events(code, d):
                m = parse_event(ev)
                if m and m["id"] not in seen:
                    seen.add(m["id"])
                    finished.append((label, m))
    finished.sort(key=lambda x: x[1]["dt"])
    print("FINISHED FOUND:", len(finished))

    if TEST_MODE:
        print("TEST MODE: sending last 3 finished matches")
        post(finished[-3:], "O'YIN NATIJALARI", "✅ O'yin natijalari")
        return

    fresh = [(l, m) for l, m in finished if f"espn-{m['id']}" not in sent]
    if not fresh:
        print("NOTHING NEW (results)")
        return
    for mid in post(fresh, "O'YIN NATIJALARI", "✅ O'yin natijalari"):
        sent.add(f"espn-{mid}")


def post_upcoming(now, sent):
    """Программа на сегодня — один раз в день, начиная с 08:00 по Ташкенту."""
    key = f"upcoming-{now:%Y-%m-%d}"
    if TEST_MODE:
        key = None  # в тестовом режиме отправляем всегда
    elif now.hour < 8 or key in sent:
        return

    today = now.strftime("%Y-%m-%d")
    items, seen = [], set()
    for code, label in LEAGUES.items():
        for ev in get_events(code, today):
            m = parse_event(ev, upcoming=True)
            if m and m["id"] not in seen:
                seen.add(m["id"])
                items.append((label, m))
    items.sort(key=lambda x: x[1]["dt"])
    print("UPCOMING FOUND:", len(items))

    if not items:
        if key:
            sent.add(key)  # сегодня матчей нет — не проверяем до завтра
        return
    items = select_main(items)
    if post(items, "BUGUNGI ASOSIY O'YINLAR", "📅 Bugun bo'lib o'tadigan asosiy o'yinlar ro'yxati.", now) and key:
        sent.add(key)


def main():
    now = datetime.now(TASHKENT)
    sent = load_sent()
    post_finished(now, sent)
    post_upcoming(now, sent)
    if not TEST_MODE:
        save_sent(sent)


if __name__ == "__main__":
    main()
