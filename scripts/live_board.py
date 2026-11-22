"""Bugungi o'yinlar — bitta "jonli" xabar: har kuni yangi xabar yuboriladi,
keyin bot uni o'zi tahrirlab turadi (hisob, daqiqa, "Yakunlandi").

Har bir o'yin nomi — o'yin sahifasiga havola (ESPN: hisob, tarkiblar, voqealar).
"""
import os
import json
import html
import hashlib
import requests
from datetime import datetime, timedelta

from post_results import LEAGUES, SHORT, TASHKENT, MONTHS, get_events, BOT_TOKEN, CHANNEL_ID, GROUP_ID

STATE_FILE = "live.json"
DRY_RUN = os.environ.get("DRY_RUN") == "1"
MAX_LEN = 3800  # Telegram limiti 4096

ENG = "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F"
FLAGS = {
    "eng.1": ENG, "esp.1": "🇪🇸", "ita.1": "🇮🇹", "ger.1": "🇩🇪", "fra.1": "🇫🇷",
    "por.1": "🇵🇹", "ned.1": "🇳🇱", "tur.1": "🇹🇷", "ksa.1": "🇸🇦",
    "uefa.champions": "🏆", "uefa.europa": "🏆", "uefa.europa.conf": "🏆",
}
CANCELLED = {"STATUS_POSTPONED", "STATUS_CANCELED", "STATUS_CANCELLED",
             "STATUS_ABANDONED", "STATUS_SUSPENDED"}


def league_title(label):
    t = label.title().replace("Uefa", "UEFA")
    return t


def team(name):
    return SHORT.get(name, name)


def parse(ev):
    comp = ev["competitions"][0]
    st = comp["status"]
    t = st["type"]
    teams = {c["homeAway"]: c for c in comp["competitors"]}
    home, away = teams["home"], teams["away"]
    dt = datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).astimezone(TASHKENT)
    link = None
    for l in ev.get("links", []):
        if "summary" in l.get("rel", []) and l.get("href"):
            link = l["href"]
            break
    if not link:
        link = f"https://www.espn.com/soccer/match/_/gameId/{ev['id']}"
    return {
        "id": ev["id"], "dt": dt, "link": link,
        "home": team(home["team"]["displayName"]),
        "away": team(away["team"]["displayName"]),
        "hg": int(float(home.get("score", 0) or 0)),
        "ag": int(float(away.get("score", 0) or 0)),
        "state": t.get("state"), "name": t.get("name", ""),
        "clock": st.get("displayClock", ""),
    }


def match_line(m):
    title = f'<a href="{html.escape(m["link"])}">{html.escape(m["home"], quote=False)} — {html.escape(m["away"], quote=False)}</a>'
    score = f'{m["hg"]}:{m["ag"]}'
    if m["name"] in CANCELLED:
        return f"❌ {title} <i>(qoldirildi)</i>"
    if m["state"] == "post":
        extra = {"STATUS_FINAL_AET": " <i>(qo'shimcha vaqt)</i>",
                 "STATUS_FINAL_PEN": " <i>(penaltilar)</i>"}.get(m["name"], "")
        return f"✅ {title} <b>{score}</b>{extra}"
    if m["state"] == "in":
        if m["name"] == "STATUS_HALFTIME":
            return f"🟡 Tanaffus {title} <b>{score}</b>"
        return f"🟢 {html.escape(m['clock'], quote=False)} {title} <b>{score}</b>"
    return f"⏰ {m['dt']:%H:%M} {title}"


def collect(now):
    today = now.date()
    dates = [(now + timedelta(days=d)).strftime("%Y-%m-%d") for d in (-1, 0, 1)]
    out, seen = {}, set()
    for code in LEAGUES:
        for ds in dates:
            for ev in get_events(code, ds):
                if ev["id"] in seen:
                    continue
                seen.add(ev["id"])
                try:
                    m = parse(ev)
                except Exception as e:
                    print("PARSE ERROR", ev.get("id"), e)
                    continue
                if m["dt"].date() == today:  # Toshkent sanasi bo'yicha
                    out.setdefault(code, []).append(m)
    for ms in out.values():
        ms.sort(key=lambda m: m["dt"])
    return out


def build_texts(now, by_league):
    if not by_league:
        return []
    head = (f"<b>⚽ Futbol / o'yinlar jadvali</b>\n"
            f"<b>{now.day}-{MONTHS[now.month].lower()}</b> · jonli yangilanadi\n"
            f"🟢 o'yin ketmoqda · ✅ yakunlandi · ⏰ boshlanadi\n")
    foot = "\n\n<b>FUTBOL OLAMI</b> — Futbol haqida hammasi!"
    texts, cur = [], head
    for code, label in LEAGUES.items():
        ms = by_league.get(code)
        if not ms:
            continue
        hdr = f"\n{FLAGS.get(code, '⚽')} <i>{html.escape(league_title(label), quote=False)}</i>\n"
        first = True
        for m in ms:
            line = match_line(m) + "\n"
            add = (hdr if first else "") + line
            if len(cur) + len(add) + len(foot) > MAX_LEN and cur != head:
                texts.append(cur.rstrip("\n") + foot)
                cur = head
                add = hdr + line
            cur += add
            first = False
    texts.append(cur.rstrip("\n") + foot)
    return texts


def tg(method, **kw):
    r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", data=kw, timeout=30)
    try:
        return r.json()
    except Exception:
        return {"ok": False, "description": r.text[:200]}


def send_new(chat, text):
    r = tg("sendMessage", chat_id=chat, text=text, parse_mode="HTML", disable_web_page_preview="true")
    print("SEND", chat, r.get("ok"), r.get("description", ""))
    return r["result"]["message_id"] if r.get("ok") else None


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def update_chat(state, chat, today, texts):
    st = state.get(chat)
    if not st or st.get("date") != today:
        st = state[chat] = {"date": today, "msgs": []}
    msgs = st["msgs"]
    for i, text in enumerate(texts):
        h = hashlib.md5(text.encode("utf-8")).hexdigest()
        if i < len(msgs):
            if msgs[i]["hash"] == h:
                continue
            r = tg("editMessageText", chat_id=chat, message_id=msgs[i]["id"], text=text,
                   parse_mode="HTML", disable_web_page_preview="true")
            print("EDIT", chat, msgs[i]["id"], r.get("ok"), r.get("description", ""))
            if r.get("ok") or "not modified" in r.get("description", ""):
                msgs[i]["hash"] = h
            else:  # xabar o'chirilgan bo'lishi mumkin — yangisini yuboramiz
                mid = send_new(chat, text)
                if mid:
                    msgs[i] = {"id": mid, "hash": h}
        else:
            mid = send_new(chat, text)
            if mid:
                msgs.append({"id": mid, "hash": h})


def main():
    now = datetime.now(TASHKENT)
    by_league = collect(now)
    texts = build_texts(now, by_league)
    print("MATCHES:", sum(len(v) for v in by_league.values()), "MESSAGES:", len(texts))
    if DRY_RUN:
        for t in texts:
            print("-" * 40)
            print(t)
        return
    if not texts:
        return
    state = load_state()
    chats = [CHANNEL_ID] + ([GROUP_ID] if GROUP_ID else [])
    for chat in chats:
        update_chat(state, chat, now.strftime("%Y-%m-%d"), texts)
    save_state(state)


if __name__ == "__main__":
    main()
