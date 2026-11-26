"""Tur tugagach — liga turnir jadvali (rasm). Faqat ichki chempionatlar.

Tur tugagan deb hisoblanadi: oxirgi 30 soat ichida o'yinlar tugagan, hozir o'yin ketmayapti va
keyingi 40 soat ichida shu ligada o'yin yo'q. Har tur uchun bir marta, bir ishga tushishda bitta liga.
"""
import html
import requests
from datetime import timedelta

from PIL import Image, ImageDraw

from post_results import (LEAGUES, LEAGUE_STYLE, TASHKENT, MONTHS, DAYS, F, W, get_events, get_logo, fit_text,
                          channel_info, league_title, send_photo, paste_logo, TEST_MODE)

# O'zbekiston terma jamoasi ishtirok etadigan guruh bosqichi turnirlari — o'yindan keyin O'zbekiston guruhi jadvali
GROUP_LEAGUES = ["fifa.world.u17", "fifa.world.u20", "fifa.world"]
GROUP_AFTER_HOURS = 30
TABLE_LEAGUES = ["eng.1", "esp.1", "ita.1", "ger.1", "fra.1", "por.1", "ned.1", "tur.1", "ksa.1"]
STANDINGS = "https://site.api.espn.com/apis/v2/sports/soccer/{code}/standings"
AFTER_HOURS, BEFORE_HOURS = 30, 40


def round_key(code, now):
    """Tur yakunlangan bo'lsa — noyob kalit, aks holda None."""
    last_done, busy = None, False
    for off in (-2, -1, 0, 1, 2):
        d = (now + timedelta(days=off)).strftime("%Y-%m-%d")
        for ev in get_events(code, d):
            try:
                st = ev["competitions"][0]["status"]["type"].get("state")
                from datetime import datetime
                dt = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(TASHKENT)
            except Exception:
                continue
            hrs = (dt - now).total_seconds() / 3600
            if st == "in" or (st == "pre" and hrs < 0 and hrs > -3):
                busy = True
            elif st == "pre" and 0 <= hrs <= BEFORE_HOURS:
                busy = True
            elif st == "post" and -AFTER_HOURS <= hrs <= 0:
                if last_done is None or dt > last_done:
                    last_done = dt
    if busy or last_done is None:
        return None
    return f"table-{code}-{last_done.strftime('%Y%m%d')}"


def fetch_table(code, team=None):
    """Liga jadvali. team berilsa — shu jamoa turgan guruh jadvali (guruh nomi bilan birga qaytadi)."""
    group = ""
    try:
        r = requests.get(STANDINGS.format(code=code), timeout=30)
        r.raise_for_status()
        children = r.json()["children"]
        child = max(children, key=lambda c: len(c.get("standings", {}).get("entries", [])))  # eng ko'p jamoali jadval (ЛЧ da bir nechta bo'lim bor)
        if team:
            child = next(c for c in children
                         if any(team in (en.get("team", {}).get("displayName", "") or "").lower()
                                for en in c["standings"]["entries"]))
            group = child.get("name", "")
        entries = child["standings"]["entries"]
    except Exception as e:
        print("STANDINGS ERROR", code, e)
        return ([], "") if team else []
    rows = []
    for e in entries:
        st = {s["name"]: s.get("value") for s in e.get("stats", [])}
        team = e.get("team", {})
        logos = team.get("logos") or [{}]
        note = e.get("note") or {}
        try:
            rows.append({"rank": int(st.get("rank") or 0), "name": team.get("displayName", "?"),
                         "logo": logos[0].get("href"), "p": int(st.get("gamesPlayed") or 0),
                         "w": int(st.get("wins") or 0), "d": int(st.get("ties") or 0), "l": int(st.get("losses") or 0),
                         "gd": int(st.get("pointDifferential") or 0), "pts": int(st.get("points") or 0),
                         "color": note.get("color"), "zone": note.get("description", "")})
        except (TypeError, ValueError):
            continue
    rows.sort(key=lambda r: (r["rank"] or 99, -r["pts"]))
    return (rows, group) if team else rows


ZONES = {"champions league": "Chempionlar Ligasi", "europa league": "Yevropa Ligasi",
         "conference league": "Konferensiyalar Ligasi", "relegation": "Pastki ligaga tushish",
         "europa conference league": "Konferensiyalar Ligasi", "relegation playoff": "Tushish pley-offi",
         "champions league qualifying": "Chempionlar Ligasi saralash", "promotion": "Yuqori ligaga chiqish"}


def zone_uz(z):
    return ZONES.get((z or "").strip().lower(), z)


def _hex(c, default=None):
    try:
        c = c.lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return default


def make_table_image(code, rows, now, title_text=None, sub_text="TURNIR JADVALI"):
    top, step, foot_h = 330, 62, 190
    legend = []
    for r in rows:
        if r["color"] and r["zone"] and r["zone"] not in [z for _, z in legend]:
            legend.append((_hex(r["color"]), r["zone"]))
    leg_h = 44 * len(legend) + (20 if legend else 0)
    height = top + 50 + len(rows) * step + leg_h + foot_h
    dark, accent = LEAGUE_STYLE.get(code, ((10, 40, 70), (75, 150, 220)))
    img = Image.new("RGBA", (W, height), dark + (255,))
    d = ImageDraw.Draw(img, "RGBA")
    for yy in range(height):
        k = yy / max(1, height - 1)
        d.line((0, yy, W, yy), fill=(int(dark[0] * (1 - 0.55 * k)), int(dark[1] * (1 - 0.55 * k)),
                                      int(dark[2] * (1 - 0.55 * k)), 255))
    if not paste_logo(img, 105, 92, 104):
        d.ellipse((55, 42, 155, 142), fill=(10, 72, 112, 130), outline=(70, 185, 240, 230), width=3)
        d.text((82, 59), "F", font=F(50, True), fill=(255, 255, 255, 255))
    d.text((185, 55), "FUTBOL OLAMI", font=F(48, True), fill=(245, 250, 255, 255))
    d.text((188, 112), "Futbol haqida hammasi!", font=F(26), fill=(150, 215, 250, 255))

    title, tf = fit_text(d, title_text or league_title(LEAGUES[code]), W - 110, 40, 26)
    d.text((55, 190), title, font=tf, fill=(255, 255, 255, 255))
    d.text((55, 250), sub_text, font=F(34, True), fill=accent + (255,))
    d.text((W - 55, 262), f"{now.strftime('%d.%m.%Y')} · {DAYS[now.weekday()]}", font=F(24),
           fill=(200, 225, 240, 255), anchor="rm")

    # ustunlar
    cols = [("O'", 640), ("G'", 710), ("D", 775), ("M", 840), ("+/-", 925), ("OCH", 1020)]
    hy = top + 20
    d.text((60, hy), "#", font=F(24, True), fill=(190, 215, 235, 255), anchor="lm")
    d.text((190, hy), "JAMOA", font=F(24, True), fill=(190, 215, 235, 255), anchor="lm")
    for name, x in cols:
        d.text((x, hy), name, font=F(24, True), fill=(190, 215, 235, 255), anchor="mm")
    y = top + 50
    for i, r in enumerate(rows):
        if i % 2 == 0:
            d.rounded_rectangle((40, y, W - 40, y + step - 4), 12, fill=(0, 0, 0, 70))
        col = _hex(r["color"])
        if col:
            d.rounded_rectangle((40, y + 4, 50, y + step - 8), 4, fill=col + (255,))
        cy = y + step // 2 - 2
        d.text((88, cy), str(r["rank"] or i + 1), font=F(30, True), fill=(255, 255, 255, 255), anchor="mm")
        lg = get_logo(r["logo"], 44)
        if lg:
            img.alpha_composite(lg, (int(130 - lg.width / 2), int(cy - lg.height / 2)))
            d = ImageDraw.Draw(img, "RGBA")
        nm, nf = fit_text(d, r["name"], 330, 31, 21)
        d.text((190, cy), nm, font=nf, fill=(255, 255, 255, 255), anchor="lm")
        vals = [r["p"], r["w"], r["d"], r["l"], f"{r['gd']:+d}" if r["gd"] else "0", r["pts"]]
        for (name, x), v in zip(cols, vals):
            last = name == "OCH"
            d.text((x, cy), str(v), font=F(32 if last else 29, True),
                   fill=(255, 215, 90, 255) if last else (235, 245, 252, 255), anchor="mm")
        y += step
    y += 20
    for col, text in legend:
        d.rounded_rectangle((60, y + 6, 78, y + 30), 4, fill=(col or (150, 150, 150)) + (255,))
        d.text((95, y + 18), zone_uz(text), font=F(24), fill=(225, 238, 248, 255), anchor="lm")
        y += 44
    fy = height - foot_h + 20
    d.line((60, fy, W - 60, fy), fill=(255, 255, 255, 90), width=2)
    _, handle = channel_info()
    d.text((70, fy + 40), "Futbol bizni birlashtiradi!", font=F(33, True), fill=(238, 248, 255, 255), anchor="lm")
    tag = f"Telegram: {handle}" if handle else "Futbol olami  •  Futbol haqida hammasi!"
    d.text((70, fy + 98), tag, font=F(32, True), fill=(110, 205, 255, 255), anchor="lm")
    return img.convert("RGB")


def caption(code):
    link, _ = channel_info()
    e = html.escape
    lines = [f"📊 <b>{e(league_title(LEAGUES[code]), quote=False)}</b>", "Tur yakunlandi — turnir jadvali"]
    lines.append(f'\n👉 <a href="{e(link)}">FUTBOL OLAMI</a> 👈' if link else "\n<b>FUTBOL OLAMI</b>")
    return "\n".join(lines)


def post_tables(now, sent):
    """Tugagan har bir tur uchun jadval. Bir ishga tushishda bitta jadval (kanalni to'ldirmaslik uchun)."""
    for code in TABLE_LEAGUES:
        key = round_key(code, now)
        if not key or key in sent:
            continue
        rows = fetch_table(code)
        if len(rows) < 8:
            continue
        print("TABLE:", code, key)
        if not TEST_MODE:
            if send_photo(make_table_image(code, rows, now), caption(code)):
                sent.add(key)
        return


def group_title(group):
    """'Group E' -> 'E GURUHI'."""
    g = (group or "").strip()
    return (g.split()[-1].upper() + " GURUHI") if g else "GURUH"


def post_group_tables(now, sent):
    """O'zbekiston o'yini tugagach — uning guruhi jadvali (har o'yin uchun bir marta)."""
    for code in GROUP_LEAGUES:
        for off in (-1, 0):
            d = (now + timedelta(days=off)).strftime("%Y-%m-%d")
            for ev in get_events(code, d):
                try:
                    comp = ev["competitions"][0]
                    names = " ".join(c["team"]["displayName"] for c in comp["competitors"]).lower()
                    if "uzbekistan" not in names:
                        continue
                    if comp["status"]["type"].get("state") != "post":
                        continue
                    from datetime import datetime
                    dt = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(TASHKENT)
                except Exception:
                    continue
                hrs = (dt - now).total_seconds() / 3600
                key = f"group-{code}-{ev['id']}"
                if key in sent or not (-GROUP_AFTER_HOURS <= hrs <= -2.0):
                    continue
                rows, group = fetch_table(code, "uzbekistan")
                if len(rows) < 3:
                    continue
                # jadval yangilanmagan bo'lsa (O'zbekiston o'yini hisobga olinmagan) — keyingi safar
                if not any("uzbekistan" in r["name"].lower() and r["p"] > 0 for r in rows):
                    continue
                print("GROUP TABLE:", code, key)
                if not TEST_MODE:
                    title = f"{league_title(LEAGUES[code])}"
                    img = make_table_image(code, rows, now, title_text=title, sub_text=group_title(group))
                    link, _ = channel_info()
                    cap = (f"📊 <b>{html.escape(title, quote=False)} · {html.escape(group_title(group), quote=False)}</b>\n"
                           "O'zbekiston o'yinidan keyin — guruh jadvali"
                           + (f'\n\n👉 <a href="{html.escape(link)}">FUTBOL OLAMI</a> 👈' if link else "\n\n<b>FUTBOL OLAMI</b>"))
                    if send_photo(img, cap):
                        sent.add(key)
                return
