"""Jonli gollar: top klublar o'yinida gol urilsa — darhol rasm (LIVE, daqiqa, joriy hisob).

Har daqiqada ishga tushadi. Har 10 daqiqada barcha ligalar skanerlanadi (qaysi top o'yinlar
ketayotgani/boshlanayotganini bilish uchun), oraliqda faqat shu ligalar so'raladi.
"""
import os
import re
import json
import time
import html
import requests
from datetime import datetime, timedelta

import goal_clips
from goal_video import make_goal_video
from post_results import (BOT_TOKEN, CHANNEL_ID, GROUP_ID, LEAGUES, TASHKENT, get_events, parse_event, basic_event, is_top,
                          make_result_card, league_title, send_photo, channel_info, TEST_MODE)

STATE_FILE = "live.json"
LIVE_GIF = os.environ.get("LIVE_GIF", "0") == "1"  # "1" — animatsion GIF; standart: "GOOOOL!" yozuvli oddiy rasm
SCAN_EVERY_SEC = 600
FIRST_SIGHT_WINDOW_MIN = 3  # bot o'yin o'rtasida birinchi marta ko'rsa — faqat so'nggi 3 daqiqadagi gollarni yuboradi


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(st):
    st["matches"] = dict(list(st.get("matches", {}).items())[-100:])
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False)


def minute_of(text):
    """"67'" -> 67, "90'+4'" -> 94."""
    nums = [int(x) for x in re.findall(r"\d+", text or "")]
    return sum(nums[:2]) if nums else 0


def goal_title(g):
    return "AVTOGOL!" if g["og"] else "GOL! (penalti)" if g["pen"] else "GOL!"


def caption(label, m, g, minute):
    e = html.escape
    link, _ = channel_info()
    lines = [f"🔴 <b>LIVE · {e(minute, quote=False)}</b>",
             f"⚽ <b>{e(m['home'], quote=False)} {m['hg']}:{m['ag']} {e(m['away'], quote=False)}</b>",
             f"🏆 {e(league_title(label), quote=False)}"]
    if g and g.get("name"):
        tail = " (penalti)" if g["pen"] else " (avtogol)" if g["og"] else ""
        lines.append(f"\n⚽ Gol: {e(g['name'], quote=False)}{tail} {e(g['min'], quote=False)}")
    lines.append(f'\n🔗 <a href="{e(m["link"])}">Statistika</a>')
    lines.append(f'\n👉 <a href="{e(link)}">FUTBOL OLAMI</a> 👈' if link else "\n<b>FUTBOL OLAMI</b>")
    return "\n".join(lines)


def _send_gif(chat_id, data, cap):
    r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendAnimation",
                      data={"chat_id": chat_id, "caption": cap, "parse_mode": "HTML"},
                      files={"animation": ("gol.gif", data, "image/gif")}, timeout=60)
    print("TELEGRAM gif", chat_id, ":", r.status_code, r.text[:150])
    return r.ok


def post_goal(label, m, g, hg, ag, upto, minute, state=None, code=None):
    """Gol uchun animatsion GIF (bo'lmasa rasm): o'sha paytdagi hisob va shu paytgacha bo'lgan voqealar."""
    snap = dict(m, hg=hg, ag=ag, events=m["events"][:upto])
    word = "AVTOGOL!" if g and g["og"] else "GOOOOL!"
    live = {"min": minute, "title": goal_title(g) if g else "GOL!", "name": g["name"] if g else "",
            "banner": (word, (255, 205, 70))}
    img = make_result_card(label, snap, live)
    cap = caption(label, snap, g, minute)
    if LIVE_GIF:
        gif = make_goal_video(img, word)
        if gif and _send_gif(CHANNEL_ID, gif, cap):
            if GROUP_ID:
                _send_gif(GROUP_ID, gif, cap)
            return {"ids": {}, "cap": cap}
    ids = send_photo(img, cap)
    if state is not None:
        goal_clips.register(state, ids, code, m, g, hg, ag, minute)
    return {"ids": ids, "cap": cap} if ids else None


def post_red(label, m, e, hg, ag, upto):
    """Qizil kartochka: hisob o'zgarmaydi, lekin rasmda qizil plashka."""
    snap = dict(m, hg=hg, ag=ag, events=m["events"][:upto])
    team = m["home"] if e["side"] == "home" else m["away"]
    live = {"min": e["min"], "title": f"QIZIL KARTOCHKA · {team.upper()}", "name": e["name"] or "Chetlatildi", "red": True,
            "banner": ("QIZIL KARTOCHKA!", (255, 75, 75))}
    img = make_result_card(label, snap, live)
    ee = html.escape
    link, _ = channel_info()
    cap = [f"🔴 <b>LIVE · {ee(e['min'], quote=False)}</b>",
           f"🟥 <b>QIZIL KARTOCHKA!</b> {ee(e['name'] or '', quote=False)} ({ee(team, quote=False)})",
           f"⚽ <b>{ee(m['home'], quote=False)} {hg}:{ag} {ee(m['away'], quote=False)}</b>",
           f"🏆 {ee(league_title(label), quote=False)}",
           f'\n🔗 <a href="{ee(m["link"])}">Statistika</a>',
           f'\n👉 <a href="{ee(link)}">FUTBOL OLAMI</a> 👈' if link else "\n<b>FUTBOL OLAMI</b>"]
    return bool(send_photo(img, "\n".join(cap)))


def _tg(method, **data):
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}", json=data, timeout=30)
        print("TELEGRAM", method, data.get("chat_id"), ":", r.status_code, r.text[:150])
        return r.ok
    except Exception as ex:
        print("TELEGRAM", method, "xato:", ex)
        return False


def post_cancel(label, m, p):
    """VAR gol(ni) bekor qildi: eski postni belgilaydi va to'g'ri hisob bilan javob yuboradi."""
    e = html.escape
    link, _ = channel_info()
    who = ""
    if p and p.get("name"):
        tail = " (avtogol)" if p.get("og") else ""
        who = f"\n{e(p['name'], quote=False)}{tail} {e(p.get('min', ''), quote=False)}"
    lines = ["❌ <b>GOL BEKOR QILINDI</b> (VAR)" + who,
             f"⚽ <b>{e(m['home'], quote=False)} {m['hg']}:{m['ag']} {e(m['away'], quote=False)}</b>",
             f"🏆 {e(league_title(label), quote=False)}",
             f'\n🔗 <a href="{e(m["link"])}">Statistika</a>',
             f'\n👉 <a href="{e(link)}">FUTBOL OLAMI</a> 👈' if link else "\n<b>FUTBOL OLAMI</b>"]
    text = "\n".join(lines)
    chats = [CHANNEL_ID] + ([GROUP_ID] if GROUP_ID else [])
    ids = (p or {}).get("ids") or {}
    for chat in chats:
        mid = ids.get(chat) or ids.get(str(chat))
        if mid and p.get("cap"):
            _tg("editMessageCaption", chat_id=chat, message_id=mid, parse_mode="HTML",
                caption="❌ <b>BEKOR QILINDI (VAR)</b>\n" + p["cap"])
        _tg("sendMessage", chat_id=chat, text=text, parse_mode="HTML", link_preview_options={"is_disabled": True},
            **({"reply_parameters": {"message_id": mid, "allow_sending_without_reply": True}} if mid else {}))
        time.sleep(1)


def check_cancelled(label, m, rec, state):
    """Avval yuborilgan gol voqealar ro'yxatidan yo'qolsa va hisob kamaysa (VAR) — bekor qilinganini e'lon qiladi.
    API xatosidan himoya: 2 ta ketma-ket so'rovda tasdiqlanishi kerak."""
    cur = {f"{e['side']}|{e['name']}|{e['min']}|{int(e['og'])}" for e in m["events"] if e["kind"] == "goal"}
    seen_goals = [k for k in rec["seen"] if not k.startswith("red|")]
    accounted = len(seen_goals) + rec["generic"]
    total = m["hg"] + m["ag"]
    if total >= accounted:
        rec["cx"] = 0
        return
    rec["cx"] = rec.get("cx", 0) + 1
    if rec["cx"] < 2:
        return
    rec["cx"] = 0
    n = accounted - total
    missing = [k for k in seen_goals if k not in cur]
    # nom/ism keyin to'ldirilgan bo'lsa (bir xil jamoa va daqiqa) — bu bekor qilish emas, eski kalit
    stale = [k for k in missing if any(c.split("|")[0] == k.split("|")[0] and c.split("|")[2] == k.split("|")[2]
                                        and c in rec["seen"] for c in cur)]
    for k in stale:
        rec["seen"].remove(k)
        n -= 1
        missing.remove(k)
    for k in missing[-n:] if n > 0 else []:
        rec["seen"].remove(k)
        n -= 1
        p = next((x for x in rec.get("posted", []) if x["key"] == k and not x.get("cancelled")), None)
        print("GOAL CANCELLED:", m["home"], m["hg"], m["ag"], m["away"], k)
        if p:
            p["cancelled"] = True
            for it in state.get("goal_clips", []):  # bekor qilingan gol uchun video qidirmaymiz
                if it.get("ids") == p.get("ids"):
                    it["done"] = True
            if not TEST_MODE:
                post_cancel(label, m, p)
    while n > 0 and rec["generic"] > 0:  # tafsilotsiz yuborilgan gol bekor bo'ldi
        rec["generic"] -= 1
        n -= 1
        print("GOAL CANCELLED (no details):", m["home"], m["hg"], m["ag"], m["away"])
        if not TEST_MODE:
            post_cancel(label, m, None)


def process_live(label, ev, state, code=None):
    m = parse_event(ev, live=True)
    if not m:
        return
    m["link"] = next((l["href"] for l in ev.get("links", []) if "summary" in l.get("rel", []) and l.get("href")),
                     f"https://www.espn.com/soccer/match/_/gameId/{m['id']}")
    rec = state.setdefault("matches", {}).get(m["id"])
    first_sight = rec is None
    if first_sight:
        rec = state["matches"][m["id"]] = {"seen": [], "generic": 0, "gap": 0}
    now_min = minute_of(m["clock"])
    events = m["events"]
    hg = ag = 0
    for idx, e in enumerate(events):
        if e["kind"] == "red":
            rkey = f"red|{e['side']}|{e['name']}|{e['min']}"
            if rkey in rec["seen"]:
                continue
            rec["seen"].append(rkey)
            rec["reds"] = rec.get("reds", 0) + 1
            if first_sight and now_min - minute_of(e["min"]) > FIRST_SIGHT_WINDOW_MIN:
                continue
            print("RED:", m["home"], m["away"], e["name"], e["min"])
            if not TEST_MODE:
                post_red(label, m, e, hg, ag, idx + 1)
                time.sleep(3.5)
            continue
        if e["kind"] != "goal":
            continue
        hg, ag = (hg + 1, ag) if e["side"] == "home" else (hg, ag + 1)
        key = f"{e['side']}|{e['name']}|{e['min']}|{int(e['og'])}"
        if key in rec["seen"]:
            continue
        rec["seen"].append(key)
        if rec["generic"] > 0:  # bu gol avval ma'lumotsiz yuborilgan edi
            rec["generic"] -= 1
            continue
        if first_sight and now_min - minute_of(e["min"]) > FIRST_SIGHT_WINDOW_MIN:
            continue  # eski gol — takrorlab yubormaymiz
        print("GOAL:", m["home"], hg, ag, m["away"], e["name"], e["min"])
        if not TEST_MODE:
            res = post_goal(label, m, e, hg, ag, idx + 1, e["min"], state, code)
            if res:
                rec.setdefault("posted", []).append({"key": key, "name": e["name"], "min": e["min"], "og": e["og"],
                                                      "ids": res["ids"], "cap": res["cap"]})
                rec["posted"] = rec["posted"][-12:]
            time.sleep(3.5)
    if not first_sight:
        check_cancelled(label, m, rec, state)
    # tafsilotsiz gol: hisob oshgan, lekin voqea ro'yxatida yo'q (2 ta ketma-ket so'rovdan keyin yuboriladi)
    accounted = sum(1 for k in rec["seen"] if not k.startswith("red|")) + rec["generic"]
    total = m["hg"] + m["ag"]
    if total > accounted and not first_sight:
        rec["gap"] += 1
        if rec["gap"] >= 2:
            rec["generic"] += total - accounted
            rec["gap"] = 0
            print("GOAL (no details):", m["home"], m["hg"], m["ag"], m["away"])
            if not TEST_MODE:
                post_goal(label, m, None, m["hg"], m["ag"], len(events), m["clock"] or "", state, code)
    else:
        rec["gap"] = 0
    if first_sight and total > accounted:
        rec["generic"] += total - accounted  # eski gollar — jim o'tamiz


def main():
    now = datetime.now(TASHKENT)
    state = load_state()
    dates = [(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in (1, 0)]
    full = time.time() - state.get("scan_ts", 0) > SCAN_EVERY_SEC
    targets = [(c, d) for c in LEAGUES for d in dates] if full else [tuple(x) for x in state.get("watch", [])]
    watch = set()
    dbg = []
    for code, d in targets:
        for ev in get_events(code, d):
            try:
                b = basic_event(ev)
            except Exception as e:
                print("PARSE ERROR", ev.get("id"), e)
                continue
            if b["state"] == "in":
                dbg.append(f"{code}|{b['home']}-{b['away']}|top={is_top(b, code)}")
            if not is_top(b, code):
                continue
            mins = (b["dt"] - now).total_seconds() / 60
            if b["state"] == "in" or (b["state"] == "pre" and 0 <= mins <= 30):
                watch.add((code, d))
            if b["state"] == "in":
                try:
                    process_live(LEAGUES[code], ev, state, code)
                except Exception as e:
                    print("LIVE ERROR", ev.get("id"), e)
    state["dbg"] = {"ts": datetime.now(TASHKENT).strftime("%H:%M:%S"), "full": full, "targets": len(targets), "in_play": dbg}
    if full:
        state["dbg_full"] = state["dbg"]
        state["watch"] = sorted(watch)
        state["scan_ts"] = time.time()
    if not TEST_MODE:
        try:
            goal_clips.check(state)
        except Exception as e:
            print("GOAL CLIPS xato:", e)
        save_state(state)


if __name__ == "__main__":
    main()
