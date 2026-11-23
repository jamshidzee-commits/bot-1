import os
import json
import time
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
ESPN_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/soccer/{code}/summary"
SENT_FILE = "sent.json"
CARDS_FILE = "cards.json"
HIGHLIGHTS_FILE = "highlights.json"
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
    "afc.champions": "AFC — OSIYO CHEMPIONLAR LIGASI",
    "afc.cup": "AFC — OSIYO CHEMPIONLAR LIGASI 2",
    "usa.1": "AMERIKA — MLS",
    "fifa.world.u17": "JAHON CHEMPIONATI — U-17",
    "fifa.world.u20": "JAHON CHEMPIONATI — U-20",
    "fifa.world": "JAHON CHEMPIONATI",
    "fifa.worldq.afc": "JAHON CHEMPIONATI — OSIYO saralash",
    "afc.asian.cup": "OSIYO KUBOGI",
    "afc.cupq": "OSIYO KUBOGI — saralash",
    "fifa.friendly": "TERMA JAMOALAR — DO'STLIK O'YINLARI",
}
# Faqat O'zbekiston terma jamoalari (har qanday yosh toifasi) o'ynaydigan turnirlar
UZ_NT_CODES = ("fifa.world.u17", "fifa.world.u20", "fifa.world", "fifa.worldq.afc",
               "afc.asian.cup", "afc.cupq", "fifa.friendly")

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
    "Pakhtakor Tashkent": "Pakhtakor", "Inter Miami CF": "Inter Miami", "Navbahor Namangan": "Navbahor", "Lokomotiv Tashkent": "Lokomotiv",
}

logo_cache = {}


def F(size, bold=False):
    return ImageFont.truetype(BOLD if bold else REGULAR, size)


_LOGO = {}


def paste_logo(img, cx, cy, size):
    """Kanal emblemasi (assets/logo.png) — doira ichida, markaz (cx, cy)."""
    try:
        if "img" not in _LOGO:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "logo.png")
            _LOGO["img"] = Image.open(path).convert("RGBA")
        lg = _LOGO["img"].resize((size, size), Image.LANCZOS)
        img.alpha_composite(lg, (int(cx - size / 2), int(cy - size / 2)))
        return True
    except Exception as e:
        print("LOGO xato:", e)
        return False


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


def parse_events(comp, home, away, hg, ag):
    """Gollar (kim, qaysi daqiqada) va qizil kartochkalar. Sariq kartochkalar olinmaydi."""
    hid = str(home["team"].get("id", home.get("id", "")))
    aid = str(away["team"].get("id", away.get("id", "")))
    out = []
    for d in comp.get("details", []) or []:
        if d.get("shootout"):
            continue
        goal, red = bool(d.get("scoringPlay")), bool(d.get("redCard"))
        if not (goal or red):
            continue
        tid = str((d.get("team") or {}).get("id", ""))
        side = "home" if tid == hid else "away" if tid == aid else None
        if not side:
            continue
        ath = (d.get("athletesInvolved") or [{}])[0]
        clock = d.get("clock") or {}
        out.append({"kind": "goal" if goal else "red", "side": side,
                    "name": ath.get("shortName") or ath.get("displayName") or "",
                    "min": clock.get("displayValue", ""), "t": clock.get("value", 0) or 0,
                    "og": bool(d.get("ownGoal")), "pen": bool(d.get("penaltyKick"))})
    out.sort(key=lambda e: e["t"])

    def counts(ev):
        return (sum(1 for e in ev if e["kind"] == "goal" and e["side"] == "home"),
                sum(1 for e in ev if e["kind"] == "goal" and e["side"] == "away"))

    # avtogol qaysi jamoaga yozilishi manbada turlicha bo'lishi mumkin — yakuniy hisob bilan solishtiramiz
    if counts(out) != (hg, ag) and any(e["og"] for e in out):
        flipped = [({**e, "side": "away" if e["side"] == "home" else "home"} if e["og"] else e) for e in out]
        if counts(flipped) == (hg, ag):
            out = flipped
    return out


def match_hero(events, hg, ag):
    """O'yin qahramoni: g'olibning hal qiluvchi goli yoki 2+ gol urgan futbolchi. (ism, izoh) yoki None."""
    goals = [e for e in events if e["kind"] == "goal"]
    win = "home" if hg > ag else "away" if ag > hg else None
    tally = {}
    for e in goals:
        if not e["og"] and (win is None or e["side"] == win):
            tally[e["name"]] = tally.get(e["name"], 0) + 1
    if tally:
        name, n = max(tally.items(), key=lambda x: x[1])
        if n >= 2 and name:
            return name, "hat-trick" if n >= 3 else f"{n} gol"
    if win:
        loser = ag if win == "home" else hg
        wg = [e for e in goals if e["side"] == win]
        if len(wg) > loser:
            e = wg[loser]  # g'olibning (raqib goli + 1)-gol — hal qiluvchi gol
            if not e["og"] and e["name"]:
                return e["name"], f"hal qiluvchi gol {e['min']}"
    return None


def parse_event(ev, upcoming=False, live=False):
    comp = ev["competitions"][0]
    status = comp["status"]["type"]
    if live:
        if status.get("state") != "in":
            return None
    elif upcoming:
        # Только матчи, которые ещё не начались
        if status.get("state") != "pre":
            return None
    elif not status.get("completed"):
        return None
    teams = {c["homeAway"]: c for c in comp["competitors"]}
    home, away = teams["home"], teams["away"]
    dt = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(TASHKENT)
    link = next((l["href"] for l in ev.get("links", []) if "summary" in l.get("rel", []) and l.get("href")), None)
    return {
        "id": ev["id"],
        "dt": dt,
        "link": link or f"https://www.espn.com/soccer/match/_/gameId/{ev['id']}",
        "home": home["team"]["displayName"],
        "away": away["team"]["displayName"],
        "home_color": (home["team"].get("color"), home["team"].get("alternateColor")),
        "away_color": (away["team"].get("color"), away["team"].get("alternateColor")),
        "events": [] if upcoming else parse_events(comp, home, away,
                                                   int(float(home.get("score", 0) or 0)),
                                                   int(float(away.get("score", 0) or 0))),
        "home_logo": home["team"].get("logo"),
        "away_logo": away["team"].get("logo"),
        "hg": int(float(home.get("score", 0) or 0)),
        "ag": int(float(away.get("score", 0) or 0)),
        "note": {"STATUS_FINAL_AET": "QO'SHIMCHA VAQT",
                 "STATUS_FINAL_PEN": "PENALTILAR"}.get(status.get("name"), ""),
        "upcoming": upcoming,
        "clock": comp["status"].get("displayClock", ""),
    }


def _load_logo(url):
    """Logotipni bir marta yuklaydi (xato bo'lsa 3 marta urinadi); natija — asl rasm yoki None."""
    if url in logo_cache:
        return logo_cache[url]
    img = None
    for attempt in range(3):
        try:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            img = Image.open(BytesIO(r.content)).convert("RGBA")
            break
        except Exception as e:
            print("LOGO ERROR:", url, attempt + 1, e)
            time.sleep(1.5)
    logo_cache[url] = img
    return img


def get_logo(url, size=80):
    if not url:
        return None
    orig = _load_logo(url)
    if orig is None:
        return None
    img = orig.copy()
    img.thumbnail((size, size), Image.Resampling.LANCZOS)
    return img


def _initials(name):
    words = [w for w in (name or "").replace("-", " ").split() if w]
    return (words[0][0] + words[1][0]).upper() if len(words) > 1 else (name or "?")[:3].upper()


def draw_logo(img, url, cx, cy, size=64, name=None):
    d = ImageDraw.Draw(img, "RGBA")
    d.ellipse((cx - size // 2, cy - size // 2, cx + size // 2, cy + size // 2),
              fill=(7, 30, 47, 255), outline=(48, 145, 200, 220), width=2)
    logo = get_logo(url)
    if not logo and name:
        d.text((cx, cy), _initials(name), font=F(max(14, size // 3), True), fill=(220, 235, 245, 255), anchor="mm")
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
    "afc.champions": ((8, 64, 56), (50, 200, 150)),
    "afc.cup": ((72, 40, 18), (240, 150, 70)),
    "usa.1": ((72, 22, 52), (245, 135, 185)),
    "fifa.world.u17": ((8, 52, 96), (60, 180, 235)),
    "fifa.world.u20": ((8, 52, 96), (60, 180, 235)),
    "fifa.world": ((8, 52, 96), (60, 180, 235)),
    "fifa.worldq.afc": ((8, 52, 96), (60, 180, 235)),
    "afc.asian.cup": ((8, 52, 96), (60, 180, 235)),
    "afc.cupq": ((8, 52, 96), (60, 180, 235)),
    "fifa.friendly": ((8, 52, 96), (60, 180, 235)),
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
    elif code == "usa.1":  # AQSH: chiziqlar + ko'k burchak
        for i in range(7):
            d.rectangle((0, round(h * i / 7), w, round(h * (i + 1) / 7)), fill=(178, 34, 52) if i % 2 == 0 else (255, 255, 255))
        d.rectangle((0, 0, round(w * 0.42), round(h * 4 / 7)), fill=(60, 59, 110))
        for ix in range(4):
            for iy in range(3):
                cx, cy = w * (0.08 + ix * 0.09), h * (0.1 + iy * 0.15)
                d.ellipse((cx - 2 * k, cy - 2 * k, cx + 2 * k, cy + 2 * k), fill=(255, 255, 255))
    elif code in UZ_NT_CODES:  # O'zbekiston bayrog'i: ko'k / oq / yashil, qizil chiziqlar
        horiz([(0, 153, 181), (255, 255, 255), (30, 181, 58)], [1, 1, 1])
        d.rectangle((0, round(h / 3) - 2 * k, w, round(h / 3) + 2 * k), fill=(206, 17, 38))
        d.rectangle((0, round(h * 2 / 3) - 2 * k, w, round(h * 2 / 3) + 2 * k), fill=(206, 17, 38))
    elif code and code.startswith("afc"):  # Osiyo: yashil fon, oq doira
        d.rectangle((0, 0, w, h), fill=(0, 122, 80))
        r = h * 0.3
        d.ellipse((w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r), outline=(255, 255, 255), width=4 * k)
        d.ellipse((w / 2 - r * 0.45, h / 2 - r * 0.45, w / 2 + r * 0.45, h / 2 + r * 0.45), fill=(255, 255, 255))
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


PRIORITY = ["fifa.world", "fifa.world.u20", "fifa.world.u17", "afc.asian.cup", "fifa.worldq.afc", "afc.cupq", "fifa.friendly", "uefa.champions", "afc.champions", "eng.1", "esp.1", "ita.1", "ger.1", "fra.1",
            "uefa.europa", "uefa.europa.conf", "afc.cup", "usa.1", "ksa.1", "tur.1", "por.1", "ned.1"]
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
    draw_logo(img, m["home_logo"], 428, cy, 66, m["home"])
    draw_logo(img, m["away_logo"], 652, cy, 66, m["away"])
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

    if not paste_logo(img, 105, 92, 104):
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
    """Yuborilgan xabar id sini qaytaradi (xato bo'lsa None)."""
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto",
        data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
        files={"photo": ("futbol-olami.jpg", BytesIO(data_bytes), "image/jpeg")},
        timeout=30,
    )
    print("TELEGRAM", chat_id, ":", r.status_code, r.text[:200])
    try:
        return r.json()["result"]["message_id"] if r.ok else None
    except Exception:
        return None


def send_photo(img, caption):
    """{chat: message_id}; kanalga yuborilmasa — bo'sh dict."""
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=92, optimize=True)
    data_bytes = buf.getvalue()
    ids = {}
    mid = _send_photo_to(CHANNEL_ID, data_bytes, caption)
    if mid:
        ids[CHANNEL_ID] = mid
        if GROUP_ID:
            gid = _send_photo_to(GROUP_ID, data_bytes, caption)
            if gid:
                ids[GROUP_ID] = gid
    return ids


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


def _hex(c):
    try:
        c = c.lstrip("#")
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
    except Exception:
        return None


def team_color(pair, fallback):
    """Jamoa rangi: juda och/to'q rang o'tkazib yuboriladi (zaxira rang olinadi), hammasi shunday bo'lsa — qoraytiriladi."""
    first = None
    for c in pair:
        rgb = _hex(c)
        if not rgb:
            continue
        first = first or rgb
        lum = 0.3 * rgb[0] + 0.59 * rgb[1] + 0.11 * rgb[2]
        if 25 <= lum <= 200:
            return rgb
    if first:
        lum = 0.3 * first[0] + 0.59 * first[1] + 0.11 * first[2]
        return tuple(int(v * 0.55) for v in first) if lum > 200 else fallback
    return fallback


def _fit_name(d, text, max_w, size=30):
    for sz in range(size, 19, -1):
        f = F(sz)
        if d.textlength(text, font=f) <= max_w:
            return text, f
    f = F(20)
    while len(text) > 3 and d.textlength(text + "...", font=f) > max_w:
        text = text[:-1]
    return text + "...", f


def _ball(d, cx, cy, r=12):
    import math
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(250, 250, 250, 255), outline=(30, 30, 30, 255), width=2)
    pts = [(cx + 5.5 * math.cos(-math.pi / 2 + i * 2 * math.pi / 5),
            cy + 5.5 * math.sin(-math.pi / 2 + i * 2 * math.pi / 5)) for i in range(5)]
    d.polygon(pts, fill=(30, 30, 30, 255))


def _clash_bg(m, H, top_zone):
    """Fon — ikki jamoa qarama-qarshiligi: jamoa ranglari, diagonal chiziq, katta xira logotiplar."""
    lc = team_color(m.get("home_color", (None, None)), (30, 90, 160))
    rc = team_color(m.get("away_color", (None, None)), (160, 50, 50))
    if sum(abs(a - b) for a, b in zip(lc, rc)) < 90:  # ranglar o'xshash bo'lsa
        alt = team_color((m.get("away_color", (None, None))[1],), (160, 50, 50))
        rc = alt if sum(abs(a - b) for a, b in zip(lc, alt)) >= 90 else (170, 50, 50)

    SS = 1
    img = Image.new("RGBA", (W, H), (5, 16, 29, 255))
    # chap va o'ng yarim — diagonal chiziq bo'ylab
    left = Image.new("RGBA", (W, H), lc + (255,))
    right = Image.new("RGBA", (W, H), rc + (255,))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).polygon([(0, 0), (610, 0), (470, H), (0, H)], fill=255)
    img = Image.composite(left, right, mask)
    # to'q qoplama (matn o'qilishi uchun) + pastga qarab to'qlashish
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for yy in range(H):
        a = int(120 + 100 * yy / H)
        sd.line((0, yy, W, yy), fill=(4, 12, 22, min(a, 235)))
    img = Image.alpha_composite(img, shade)
    d = ImageDraw.Draw(img, "RGBA")
    # katta xira logotiplar
    for url, cx, side in ((m["home_logo"], 160, "l"), (m["away_logo"], 920, "r")):
        big = get_logo(url, 520)
        if big:
            ghost = big.copy()
            alpha = ghost.getchannel("A").point(lambda v: int(v * 0.16))
            ghost.putalpha(alpha)
            img.alpha_composite(ghost, (int(cx - ghost.width / 2), int(330 - ghost.height / 2)))
    d = ImageDraw.Draw(img, "RGBA")
    # urush chizig'i
    d.line([(610, 0), (610 - 140 * top_zone / H, top_zone)], fill=(255, 255, 255, 80), width=5)
    return img


def make_result_card(label, m, live=None):
    """Tugagan o'yin: fon — ikki jamoa qarama-qarshiligi (jamoa ranglari + katta logotiplar),
    hisob, gollar (daqiqa bilan), qizil kartochkalar va o'yin qahramoni."""
    events = m.get("events") or []
    hero_title = "O'YIN QAHRAMONI"
    if live:  # jonli gol: pastdagi plashkada gol urgan futbolchi
        hero, hero_title = (live.get("name") or "Gol urildi", live.get("min", "")), live.get("title", "GOL!")
    else:
        hero = match_hero(events, m["hg"], m["ag"]) if events else None
    rows = max(sum(1 for e in events if e["side"] == "home"), sum(1 for e in events if e["side"] == "away"))
    rows = min(rows, 8)
    row_h = 46
    top_zone = 640
    panel_h = (70 + rows * row_h + 20) if events else 0
    hero_h = 130 if hero else 0
    foot_h = 170
    H = top_zone + (panel_h + 30 if events else 0) + (hero_h + 30 if hero else 0) + foot_h

    img = _clash_bg(m, H, top_zone)
    d = ImageDraw.Draw(img, "RGBA")

    # sarlavha
    if not paste_logo(img, 90, 73, 76):
        d.ellipse((55, 38, 125, 108), fill=(10, 72, 112, 150), outline=(70, 185, 240, 230), width=3)
        d.text((90, 73), "F", font=F(38, True), fill=(255, 255, 255, 255), anchor="mm")
    d.text((148, 56), "FUTBOL OLAMI", font=F(38, True), fill=(245, 250, 255, 255), anchor="lm")
    d.text((148, 94), "Futbol haqida hammasi!", font=F(21), fill=(150, 215, 250, 255), anchor="lm")
    code = LEAGUE_CODE.get(label)
    img.alpha_composite(make_flag(code), (55, 140))
    d = ImageDraw.Draw(img, "RGBA")
    d.text((130, 160), league_title(label), font=F(30, True), fill=(250, 252, 255, 255), anchor="lm")
    dt = m["dt"]
    d.text((W - 55, 160), f"{dt.strftime('%d.%m.%Y')} · {DAYS[dt.weekday()]}", font=F(24),
           fill=(200, 225, 240, 255), anchor="rm")

    # jamoalar, hisob
    if live:
        d.rounded_rectangle((420, 214, 660, 256), 21, fill=(215, 30, 45, 255))
        d.ellipse((440, 229, 454, 243), fill=(255, 255, 255, 255))
        d.text((552, 235), f"LIVE  {live.get('min', '')}", font=F(26, True), fill=(255, 255, 255, 255), anchor="mm")
    else:
        d.text((540, 235), "YAKUNLANDI", font=F(24, True), fill=(160, 220, 255, 255), anchor="mm")
    for url, cx, nm in ((m["home_logo"], 180, m["home"]), (m["away_logo"], 900, m["away"])):
        lg = get_logo(url, 190)
        d.ellipse((cx - 105, 270, cx + 105, 480), fill=(5, 16, 29, 150), outline=(255, 255, 255, 70), width=3)
        if lg:
            img.alpha_composite(lg, (int(cx - lg.width / 2), int(375 - lg.height / 2)))
        else:
            d.text((cx, 375), _initials(nm), font=F(64, True), fill=(220, 235, 245, 255), anchor="mm")
    d = ImageDraw.Draw(img, "RGBA")
    d.text((540, 372), f"{m['hg']} : {m['ag']}", font=F(112, True), fill=(255, 255, 255, 255), anchor="mm")
    if m.get("note"):
        d.text((540, 450), m["note"], font=F(22, True), fill=(150, 215, 250, 255), anchor="mm")
    hn, hf = fit_text(d, m["home"], 330, 36, 22)
    an, af = fit_text(d, m["away"], 330, 36, 22)
    d.text((180, 520), hn, font=hf, fill=(255, 255, 255, 255), anchor="mm")
    d.text((900, 520), an, font=af, fill=(255, 255, 255, 255), anchor="mm")

    if live and live.get("banner"):  # katta "GOOOOL!" yozuvi: nomlar va voqealar paneli oralig'ida
        btxt, bcol = live["banner"]
        bsize = 78
        bf = F(bsize, True)
        while d.textlength(btxt, font=bf) > W - 170 and bsize > 40:
            bsize -= 4
            bf = F(bsize, True)
        bw, by = d.textlength(btxt, font=bf), 590
        d.rounded_rectangle((540 - bw / 2 - 38, by - 44, 540 + bw / 2 + 38, by + 44), 26, fill=(0, 0, 0, 175),
                            outline=bcol + (255,), width=3)
        d.text((543, by + 4), btxt, font=bf, fill=(0, 0, 0, 255), anchor="mm")
        d.text((540, by), btxt, font=bf, fill=bcol + (255,), anchor="mm")

    y = top_zone
    if events:
        d.rounded_rectangle((45, y, W - 45, y + panel_h), 20, fill=(4, 12, 22, 175), outline=(255, 255, 255, 60), width=2)
        d.text((540, y + 34), "O'YIN VOQEALARI", font=F(24, True), fill=(160, 220, 255, 255), anchor="mm")
        for side, x0 in (("home", 75), ("away", 575)):
            evs = [e for e in events if e["side"] == side]
            extra = max(0, len(evs) - 8)
            for i, e in enumerate(evs[:8]):
                cy = y + 70 + i * row_h + 23
                if e["kind"] == "goal":
                    _ball(d, x0 + 12, cy)
                else:
                    d.rounded_rectangle((x0 + 3, cy - 12, x0 + 21, cy + 12), 3, fill=(225, 30, 40, 255))
                tail = " (pen.)" if e["pen"] else " (a.g.)" if e["og"] else ""
                mn = e["min"]
                mw = d.textlength(mn, font=F(28, True))
                name, f = _fit_name(d, (e["name"] or "—") + tail, 400 - mw - 40)
                d.text((x0 + 42, cy), name, font=f, fill=(250, 252, 255, 255), anchor="lm")
                d.text((x0 + 42 + d.textlength(name, font=f) + 14, cy), mn, font=F(28, True),
                       fill=(255, 215, 90, 255) if e["kind"] == "goal" else (255, 120, 120, 255), anchor="lm")
            if extra:
                d.text((x0 + 42, y + 70 + 8 * row_h + 12), f"+{extra}", font=F(22), fill=(200, 225, 240, 255), anchor="lm")
        y += panel_h + 30
    if hero:
        red = bool(live and live.get("red"))
        d.rounded_rectangle((45, y, W - 45, y + hero_h), 22, fill=(80, 10, 14, 235) if red else (70, 50, 8, 230),
                            outline=(235, 45, 55, 255) if red else (255, 205, 70, 255), width=3)
        if red:
            d.rounded_rectangle((95, y + hero_h / 2 - 28, 143, y + hero_h / 2 + 28), 6, fill=(225, 30, 40, 255))
        else:
            d.polygon(_star(120, y + hero_h / 2, 36), fill=(255, 205, 70, 255))
        d.text((190, y + 38), hero_title, font=F(22, True), fill=(255, 150, 150, 255) if red else (255, 215, 120, 255), anchor="lm")
        hname, hf2 = _fit_name(d, hero[0], 520, 42)
        d.text((190, y + 78), hname, font=F(hf2.size, True), fill=(255, 255, 255, 255), anchor="lm")
        d.text((W - 75, y + 78), hero[1], font=F(28, True), fill=(255, 150, 150, 255) if red else (255, 215, 90, 255), anchor="rm")
        y += hero_h + 30

    fy = H - foot_h + 20
    d.line((60, fy, W - 60, fy), fill=(255, 255, 255, 90), width=2)
    _, handle = channel_info()
    d.text((70, fy + 40), "Futbol bizni birlashtiradi!", font=F(33, True), fill=(238, 248, 255, 255), anchor="lm")
    tag = f"Telegram: {handle}" if handle else "Futbol olami  •  Futbol haqida hammasi!"
    d.text((70, fy + 98), tag, font=F(32, True), fill=(110, 205, 255, 255), anchor="lm")
    return img.convert("RGB")


def league_title(label):
    return label.title().replace("Uefa", "UEFA").replace("Afc", "AFC").replace("Mls", "MLS")


def load_cards():
    try:
        with open(CARDS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_cards(cards):
    with open(CARDS_FILE, "w", encoding="utf-8") as f:
        json.dump(dict(list(cards.items())[-200:]), f, ensure_ascii=False)


def load_videos():
    """highlights.py topgan rasmiy YouTube sharhlari: {o'yin id: havola}."""
    try:
        with open(HIGHLIGHTS_FILE, encoding="utf-8") as f:
            return json.load(f).get("videos", {})
    except Exception:
        return {}


def card_caption(c, video=None):
    e = html.escape
    lines = [f"✅ <b>{e(c['home'], quote=False)} {c['hg']}:{c['ag']} {e(c['away'], quote=False)}</b>",
             f"🏆 {e(league_title(c['league']), quote=False)}"]
    links = [f'🔗 <a href="{e(c["espn"])}">Statistika</a>']
    if video:
        links.append(f'▶️ <a href="{e(video)}">Obzor</a>')
    lines.append("\n" + "  ·  ".join(links))
    link, _ = channel_info()
    lines.append(f'\n<a href="{e(link)}">FUTBOL OLAMI</a> ✈️' if link else "\n<b>FUTBOL OLAMI</b>")
    return "\n".join(lines)


def post_card(label, m, cards, videos):
    """Tugagan o'yin: bitta rasm (hisob) + pastda Statistika va (bo'lsa) YouTube sharh havolasi."""
    c = {"home": m["home"], "away": m["away"], "hg": m["hg"], "ag": m["ag"],
         "league": label, "espn": m["link"]}
    video = videos.get(m["id"])
    img = make_result_card(label, m)
    ids = send_photo(img, card_caption(c, video))
    if ids and cards is not None:
        cards[m["id"]] = {**c, "ids": ids, "video": bool(video)}
    return bool(ids)


def update_cards(cards):
    """Sharh keyinroq chiqadi: topilgach, avval yuborilgan rasm ostiga 'Obzor' havolasi qo'shiladi."""
    videos = load_videos()
    for mid, c in cards.items():
        url = videos.get(mid)
        if c.get("video") or not url:
            continue
        cap = card_caption(c, url)
        done = False
        for chat, msg_id in c["ids"].items():
            r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageCaption",
                              data={"chat_id": chat, "message_id": msg_id, "caption": cap, "parse_mode": "HTML"},
                              timeout=30)
            print("EDIT CAPTION", chat, msg_id, r.status_code, r.text[:120])
            if r.ok or "not modified" in r.text:
                done = True
            time.sleep(1)
        if done:
            c["video"] = True


def post_finished(now, sent, cards):
    """Итоги матчей за вчера и сегодня — только те, что ещё не отправлены."""
    days_back = 7 if TEST_MODE else 1
    dates = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_back, -1, -1)]

    finished, seen = [], set()
    for code, label in LEAGUES.items():
        for d in dates:
            for ev in get_events(code, d):
                m = parse_event(ev)
                if m and m["id"] not in seen and league_ok(code, m):
                    seen.add(m["id"])
                    finished.append((label, m))
    finished.sort(key=lambda x: x[1]["dt"])
    print("FINISHED FOUND:", len(finished))

    if TEST_MODE:
        print("TEST MODE: sending last 3 finished matches")
        videos = load_videos()
        for label, m in finished[-3:]:
            post_card(label, m, None, videos)
            time.sleep(3.5)
        return

    fresh = [(l, m) for l, m in finished if f"espn-{m['id']}" not in sent]
    if not fresh:
        print("NOTHING NEW (results)")
        return
    videos = load_videos()
    for i, (label, m) in enumerate(fresh):
        if i:
            time.sleep(3.5)  # Telegram limiti: ~20 xabar/daqiqa
        if post_card(label, m, cards, videos):
            sent.add(f"espn-{m['id']}")


# ---------- TARKIBLAR (starting XI) ----------
# Faqat shu klublar ishtirokidagi (va barcha Chempionlar Ligasi) o'yinlar uchun tarkib yuboriladi.
# Ro'yxatni o'zgartirish mumkin — nomlar ESPN dagi inglizcha nomlar, kichik harflarda, aksentsiz.
TOP_CLUBS = {
    "real madrid", "barcelona", "atletico madrid", "manchester city", "manchester united", "liverpool",
    "arsenal", "chelsea", "tottenham hotspur", "newcastle united", "bayern munich", "borussia dortmund",
    "bayer leverkusen", "paris saint-germain", "juventus", "inter milan", "ac milan", "napoli", "as roma",
    "al nassr", "al hilal", "galatasaray", "fenerbahce", "benfica", "porto", "sporting cp", "ajax",
    "istanbul basaksehir", "basaksehir", "basaksehir fk",
    # ESPN ba'zan boshqacha yozadi
    "internazionale", "inter", "milan", "atletico de madrid", "atletico", "bayern", "bayern munchen",
    "paris saint germain", "psg", "man city", "man united", "tottenham", "newcastle", "sporting", "roma",
    "borussia dortmund", "bayer 04 leverkusen",
}
# O'zbekiston klublari (nomning bir qismi bo'yicha) — ularning barcha xalqaro o'yinlari uchun tarkib yuboriladi
UZ_CLUBS = ("pakhtakor", "nasaf", "bunyodkor", "navbahor", "agmk", "sogdiana", "neftchi", "lokomotiv tashkent")
LINEUP_BEFORE_MIN = 100  # o'yindan necha daqiqa oldin tarkibni qidirishni boshlaymiz
LINEUP_AFTER_MIN = 20    # o'yin boshlangandan keyin ham shuncha daqiqa urinamiz
POS_RANK = {"G": 0, "D": 1, "M": 2, "F": 3, "A": 3}


def _norm(t):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", (t or "").lower()) if not unicodedata.combining(c))


def _name_forms(*names):
    out = set()
    for n in names:
        n = _norm(n)
        out |= {n, n.replace("-", " ")}
    return out


def league_ok(code, m):
    """Cheklangan turnirlar: AFC — faqat O'zbekiston klublari va Al Nassr; MLS — faqat Inter Miami (Messi)."""
    forms = _name_forms(m["home"], m["away"])
    if code in UZ_NT_CODES:  # terma jamoalar turnirlari — faqat O'zbekiston (har qanday yosh)
        return any("uzbekistan" in n for n in forms)
    if code.startswith("afc."):
        return any(k in n for n in forms for k in UZ_CLUBS + ("al nassr",))
    if code == "usa.1":
        return any("inter miami" in n for n in forms)
    return True


def is_top(m, code):
    if code.startswith("afc.") or code == "usa.1" or code in UZ_NT_CODES:
        return league_ok(code, m)
    forms = _name_forms(m["home"], m["away"])
    return (code == "uefa.champions" or any(n in TOP_CLUBS for n in forms)
            or any(k in n for n in forms for k in UZ_CLUBS))


def basic_event(ev):
    comp = ev["competitions"][0]
    teams = {c["homeAway"]: c for c in comp["competitors"]}
    home, away = teams["home"], teams["away"]
    link = next((l["href"] for l in ev.get("links", []) if "summary" in l.get("rel", []) and l.get("href")), None)
    return {
        "id": ev["id"], "state": comp["status"]["type"].get("state"),
        "dt": datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(TASHKENT),
        "link": link or f"https://www.espn.com/soccer/match/_/gameId/{ev['id']}",
        "home": home["team"]["displayName"], "away": away["team"]["displayName"],
        "home_logo": home["team"].get("logo"), "away_logo": away["team"].get("logo"),
        "home_color": (home["team"].get("color"), home["team"].get("alternateColor")),
        "away_color": (away["team"].get("color"), away["team"].get("alternateColor")),
    }


def _coach_name(c):
    if isinstance(c, list):
        c = c[0] if c else None
    if isinstance(c, dict):
        return c.get("displayName") or " ".join(x for x in (c.get("firstName"), c.get("lastName")) if x)
    return c or ""


def get_lineups(code, event_id):
    """{'home': {...}, 'away': {...}} yoki None (tarkib hali e'lon qilinmagan)."""
    try:
        r = requests.get(ESPN_SUMMARY.format(code=code), params={"event": event_id}, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print("SUMMARY ERROR", event_id, e)
        return None
    out = {}
    for t in data.get("rosters", []) or []:
        side = t.get("homeAway")
        if side not in ("home", "away"):
            continue
        players = []
        for p in t.get("roster", []) or []:
            a = p.get("athlete") or {}
            players.append({"name": a.get("shortName") or a.get("displayName") or "",
                            "num": str(p.get("jersey", "") or ""),
                            "pos": ((p.get("position") or {}).get("abbreviation") or "")[:1].upper(),
                            "place": p.get("formationPlace"), "starter": bool(p.get("starter"))})
        starters = [p for p in players if p["starter"]]
        if len(starters) < 11:
            return None
        starters.sort(key=lambda p: (int(p["place"]) if str(p["place"]).isdigit() else 99, POS_RANK.get(p["pos"], 9)))
        form = t.get("formation")
        out[side] = {"formation": form if isinstance(form, str) else (form or {}).get("name", ""),
                     "starters": starters[:11], "bench": [p for p in players if not p["starter"]],
                     "coach": _coach_name(t.get("coach"))}
    return out if len(out) == 2 else None


def _wrap(d, text, font, width, max_lines=3):
    lines, cur = [], ""
    for w in text.split(", "):
        t = w if not cur else cur + ", " + w
        if d.textlength(t, font=font) <= width:
            cur = t
        else:
            lines.append(cur + ",")
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(",") + " ..."
    return lines


def make_lineup_card(label, m, lu):
    """Ikkala jamoaning boshlang'ich tarkibi: fon — jamoalar qarama-qarshiligi."""
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    bf = F(22)
    bench = {sd: _wrap(tmp, ", ".join(p["name"] for p in lu[sd]["bench"]), bf, 430) for sd in ("home", "away")}
    has_bench = any(bench.values())
    bench_h = (56 + max(len(bench["home"]), len(bench["away"])) * 30) if has_bench else 0
    has_coach = bool(lu["home"].get("coach") or lu["away"].get("coach"))
    row_h, top_zone, foot_h = 54, 570, 170
    panel_h = 70 + 11 * row_h + (52 if has_coach else 20)
    H = top_zone + panel_h + 30 + (bench_h + 30 if has_bench else 0) + foot_h

    img = _clash_bg(m, H, top_zone)
    d = ImageDraw.Draw(img, "RGBA")
    lc = team_color(m.get("home_color", (None, None)), (30, 90, 160))
    rc = team_color(m.get("away_color", (None, None)), (160, 50, 50))

    if not paste_logo(img, 90, 73, 76):
        d.ellipse((55, 38, 125, 108), fill=(10, 72, 112, 150), outline=(70, 185, 240, 230), width=3)
        d.text((90, 73), "F", font=F(38, True), fill=(255, 255, 255, 255), anchor="mm")
    d.text((148, 56), "FUTBOL OLAMI", font=F(38, True), fill=(245, 250, 255, 255), anchor="lm")
    d.text((148, 94), "Futbol haqida hammasi!", font=F(21), fill=(150, 215, 250, 255), anchor="lm")
    img.alpha_composite(make_flag(LEAGUE_CODE.get(label)), (55, 140))
    d = ImageDraw.Draw(img, "RGBA")
    d.text((130, 160), league_title(label), font=F(30, True), fill=(250, 252, 255, 255), anchor="lm")
    dt = m["dt"]
    d.text((W - 55, 160), f"{dt.strftime('%d.%m.%Y')} · {DAYS[dt.weekday()]}", font=F(24),
           fill=(200, 225, 240, 255), anchor="rm")
    d.text((540, 228), "BOSHLANG'ICH TARKIBLAR", font=F(36, True), fill=(255, 255, 255, 255), anchor="mm")

    for url, cx, nm in ((m["home_logo"], 170, m["home"]), (m["away_logo"], 910, m["away"])):
        lg = get_logo(url, 150)
        d.ellipse((cx - 82, 288, cx + 82, 452), fill=(5, 16, 29, 150), outline=(255, 255, 255, 70), width=3)
        if lg:
            img.alpha_composite(lg, (int(cx - lg.width / 2), int(370 - lg.height / 2)))
        else:
            d.text((cx, 370), _initials(nm), font=F(52, True), fill=(220, 235, 245, 255), anchor="mm")
    d = ImageDraw.Draw(img, "RGBA")
    d.text((540, 355), "VS", font=F(80, True), fill=(255, 255, 255, 255), anchor="mm")
    d.text((540, 432), dt.strftime("%H:%M"), font=F(36, True), fill=(255, 215, 90, 255), anchor="mm")
    for key, cx in (("home", 170), ("away", 910)):
        nm, nf = fit_text(d, m[key], 330, 34, 22)
        d.text((cx, 485), nm, font=nf, fill=(255, 255, 255, 255), anchor="mm")
        if lu[key].get("formation"):
            d.text((cx, 530), lu[key]["formation"], font=F(30, True), fill=(255, 215, 90, 255), anchor="mm")

    y = top_zone
    d.rounded_rectangle((45, y, W - 45, y + panel_h), 20, fill=(4, 12, 22, 185), outline=(255, 255, 255, 60), width=2)
    for side, x0, col in (("home", 70, lc), ("away", 575, rc)):
        badge = tuple(min(255, int(v * 0.6 + 100)) for v in col)
        for i, p in enumerate(lu[side]["starters"]):
            cy = y + 45 + i * row_h + 27
            d.ellipse((x0, cy - 20, x0 + 40, cy + 20), fill=badge + (255,), outline=(255, 255, 255, 220), width=2)
            d.text((x0 + 20, cy), p["num"] or "·", font=F(21, True), fill=(10, 20, 30, 255), anchor="mm")
            name, f = _fit_name(d, p["name"] or "—", 370, 30)
            d.text((x0 + 56, cy), name, font=f, fill=(250, 252, 255, 255), anchor="lm")
        if lu[side].get("coach"):
            cn, cf = _fit_name(d, "Murabbiy: " + lu[side]["coach"], 420, 24)
            d.text((x0, y + 45 + 11 * row_h + 28), cn, font=cf, fill=(160, 220, 255, 255), anchor="lm")
    d.line((540, y + 30, 540, y + panel_h - 30), fill=(255, 255, 255, 40), width=2)
    y += panel_h + 30
    if has_bench:
        d.rounded_rectangle((45, y, W - 45, y + bench_h), 20, fill=(4, 12, 22, 150), outline=(255, 255, 255, 50), width=2)
        d.text((70, y + 28), "ZAXIRADAGILAR", font=F(22, True), fill=(160, 220, 255, 255), anchor="lm")
        for side, x0 in (("home", 70), ("away", 575)):
            for j, ln in enumerate(bench[side]):
                d.text((x0, y + 64 + j * 30), ln, font=bf, fill=(225, 238, 248, 255), anchor="lm")
        y += bench_h + 30

    fy = H - foot_h + 20
    d.line((60, fy, W - 60, fy), fill=(255, 255, 255, 90), width=2)
    _, handle = channel_info()
    d.text((70, fy + 40), "Futbol bizni birlashtiradi!", font=F(33, True), fill=(238, 248, 255, 255), anchor="lm")
    tag = f"Telegram: {handle}" if handle else "Futbol olami  •  Futbol haqida hammasi!"
    d.text((70, fy + 98), tag, font=F(32, True), fill=(110, 205, 255, 255), anchor="lm")
    return img.convert("RGB")


def lineup_caption(label, m):
    e = html.escape
    link, _ = channel_info()
    return (f"📋 <b>Boshlang'ich tarkiblar</b>\n"
            f"⚽ {e(m['home'], quote=False)} — {e(m['away'], quote=False)}\n"
            f"🏆 {e(league_title(label), quote=False)} · ⏰ {m['dt']:%H:%M}\n\n"
            f'🔗 <a href="{e(m["link"])}">Statistika</a>\n\n'
            + (f'<a href="{e(link)}">FUTBOL OLAMI</a> ✈️' if link else "<b>FUTBOL OLAMI</b>"))


def post_lineups(now, sent):
    """Top klublar o'yinlari: tarkib e'lon qilinishi bilan (odatda ~1 soat oldin) — bitta rasm."""
    dates = [(now + timedelta(days=i)).strftime("%Y-%m-%d") for i in (-1, 0, 1)]
    cands, seen = [], set()
    for code, label in LEAGUES.items():
        for dstr in dates:
            for ev in get_events(code, dstr):
                try:
                    m = basic_event(ev)
                except Exception as e:
                    print("LINEUP PARSE ERROR", ev.get("id"), e)
                    continue
                if m["id"] in seen:
                    continue
                seen.add(m["id"])
                mins = (m["dt"] - now).total_seconds() / 60
                if not TEST_MODE and (m["state"] == "post" or not (-LINEUP_AFTER_MIN <= mins <= LINEUP_BEFORE_MIN)):
                    continue
                if not is_top(m, code) or (f"lineup-{m['id']}" in sent and not TEST_MODE):
                    continue
                cands.append((label, code, m))
    print("LINEUP CANDIDATES:", len(cands))
    cands.sort(key=lambda x: x[2]["dt"])
    for label, code, m in cands:
        lu = get_lineups(code, m["id"])
        if not lu:
            print("LINEUP not published yet:", m["home"], "-", m["away"])
            continue
        if send_photo(make_lineup_card(label, m, lu), lineup_caption(label, m)):
            if not TEST_MODE:
                sent.add(f"lineup-{m['id']}")
            time.sleep(3.5)
        if TEST_MODE:
            break


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
            if m and m["id"] not in seen and league_ok(code, m):
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


# ---------- KUNLIK NATIJALAR (har ertalab) ----------
DAILY_HOUR = 9  # Toshkent vaqti bilan; 08:00 dagi "bugungi o'yinlar" ro'yxatidan keyin
FLAG_EMOJI = {"eng.1": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "esp.1": "🇪🇸", "ita.1": "🇮🇹", "ger.1": "🇩🇪", "fra.1": "🇫🇷", "por.1": "🇵🇹",
              "ned.1": "🇳🇱", "tur.1": "🇹🇷", "ksa.1": "🇸🇦", "usa.1": "🇺🇸", "uefa.champions": "🇪🇺",
              "uefa.europa": "🇪🇺", "uefa.europa.conf": "🇪🇺", "afc.champions": "🌏", "afc.cup": "🌏", "fifa.world.u17": "🇺🇿", "fifa.world.u20": "🇺🇿", "fifa.world": "🇺🇿",
              "fifa.worldq.afc": "🇺🇿", "afc.asian.cup": "🇺🇿", "afc.cupq": "🇺🇿", "fifa.friendly": "🇺🇿"}


def send_text(text):
    """Matnli xabar kanalga (va guruhga). Hech bo'lmasa kanalga ketsa — True."""
    ok = False
    for chat in [CHANNEL_ID] + ([GROUP_ID] if GROUP_ID else []):
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                          data={"chat_id": chat, "text": text, "parse_mode": "HTML",
                                "disable_web_page_preview": "true"}, timeout=30)
        print("TELEGRAM text", chat, ":", r.status_code, r.text[:120])
        if chat == CHANNEL_ID:
            ok = r.ok
    return ok


def daily_results_text(items, videos):
    """Rasm ostidagi matn: har o'yin — hisob, Statistika va (bo'lsa) YouTube sharh havolasi."""
    e = html.escape
    link, _ = channel_info()
    by_league = {}
    for label, m in sorted(items, key=lambda x: x[1]["dt"]):
        by_league.setdefault(label, []).append(m)
    footer = f'\n<a href="{e(link)}">FUTBOL OLAMI</a> ✈️' if link else "\n<b>FUTBOL OLAMI</b>"
    blocks, cur = [], "📊 <b>So'nggi 24 soat natijalari</b>\n"
    for label, ms in sorted(by_league.items(), key=lambda kv: PRIORITY.index(LEAGUE_CODE.get(kv[0])) if LEAGUE_CODE.get(kv[0]) in PRIORITY else 99):
        block = f"\n{FLAG_EMOJI.get(LEAGUE_CODE.get(label), '🏆')} <b>{e(league_title(label), quote=False)}</b>\n"
        for m in ms:
            line = (f"⚽ {e(m['home'], quote=False)} <b>{m['hg']}:{m['ag']}</b> {e(m['away'], quote=False)}"
                    f"{' (' + e(m['note'], quote=False) + ')' if m.get('note') else ''}")
            links = f'📊 <a href="{e(m["link"])}">Statistika</a>'
            if videos.get(m["id"]):
                links += f'   |   ▶️ <a href="{e(videos[m["id"]])}">Obzor</a>'
            line += "\n      └ " + links + "\n"
            block += line + "\n"
        if len(cur) + len(block) > 3700:
            blocks.append(cur)
            cur = ""
        cur += block
    blocks.append(cur)
    blocks[-1] += footer
    return blocks


def post_daily_results(now, sent):
    """Har ertalab (DAILY_HOUR dan) — oxirgi 24 soatdagi barcha o'yinlar natijasi: bitta rasm (faqat hisob)
    va uning ostida alohida matn: Statistika + ▶️ Obzor."""
    key = f"daily-{now:%Y-%m-%d}"
    if TEST_MODE:
        key = None
    elif now.hour < DAILY_HOUR or key in sent:
        return
    dates = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in (2, 1, 0)]
    items, seen = [], set()
    for code, label in LEAGUES.items():
        for d_ in dates:
            for ev in get_events(code, d_):
                m = parse_event(ev)
                if (m and m["id"] not in seen and league_ok(code, m)
                        and timedelta(0) <= now - m["dt"] <= timedelta(hours=24)):
                    seen.add(m["id"])
                    items.append((label, m))
    print("DAILY RESULTS FOUND:", len(items))
    if not items:
        if key:
            sent.add(key)
        return
    items = select_main(items)
    if not post(items, "SO'NGGI 24 SOAT NATIJALARI", "📊 Kecha va tunda o'ynalgan o'yinlar natijalari.", now):
        return
    if not TEST_MODE:
        time.sleep(3)
    ok = True
    for chunk in daily_results_text(items, load_videos()):
        ok = send_text(chunk) and ok
        time.sleep(2)
    if key:
        sent.add(key)


def main():
    now = datetime.now(TASHKENT)
    sent = load_sent()
    cards = load_cards()
    post_finished(now, sent, cards)
    post_upcoming(now, sent)
    post_daily_results(now, sent)
    post_lineups(now, sent)
    try:
        from standings import post_tables, post_group_tables
        post_group_tables(now, sent)
        post_tables(now, sent)
    except Exception as e:
        print("TABLE ERROR", e)
    if not TEST_MODE:
        update_cards(cards)
        save_sent(sent)
        save_cards(cards)


if __name__ == "__main__":
    main()
