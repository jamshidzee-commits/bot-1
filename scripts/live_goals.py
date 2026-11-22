"""Jonli gollar: top klublar o'yinida gol urilsa — darhol rasm (LIVE, daqiqa, joriy hisob).

Har 2 daqiqada ishga tushadi. Har 10 daqiqada barcha ligalar skanerlanadi (qaysi top o'yinlar
ketayotgani/boshlanayotganini bilish uchun), oraliqda faqat shu ligalar so'raladi.
"""
import re
import json
import time
import html
from datetime import datetime, timedelta

from post_results import (LEAGUES, TASHKENT, get_events, parse_event, basic_event, is_top,
                          make_result_card, league_title, send_photo, channel_info, TEST_MODE)

STATE_FILE = "live.json"
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
    lines.append(f'\n🔗 <a href="{e(m["link"])}">ESPN</a>')
    lines.append(f'\n<a href="{e(link)}">FUTBOL OLAMI</a> ✈️' if link else "\n<b>FUTBOL OLAMI</b>")
    return "\n".join(lines)


def post_goal(label, m, g, hg, ag, upto, minute):
    """Gol uchun bitta rasm: o'sha paytdagi hisob va shu paytgacha bo'lgan voqealar."""
    snap = dict(m, hg=hg, ag=ag, events=m["events"][:upto])
    live = {"min": minute, "title": goal_title(g) if g else "GOL!", "name": g["name"] if g else ""}
    img = make_result_card(label, snap, live)
    return bool(send_photo(img, caption(label, snap, g, minute)))


def process_live(label, ev, state):
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
            post_goal(label, m, e, hg, ag, idx + 1, e["min"])
            time.sleep(3.5)
    # tafsilotsiz gol: hisob oshgan, lekin voqea ro'yxatida yo'q (2 ta ketma-ket so'rovdan keyin yuboriladi)
    accounted = len(rec["seen"]) + rec["generic"]
    total = m["hg"] + m["ag"]
    if total > accounted and not first_sight:
        rec["gap"] += 1
        if rec["gap"] >= 2:
            rec["generic"] += total - accounted
            rec["gap"] = 0
            print("GOAL (no details):", m["home"], m["hg"], m["ag"], m["away"])
            if not TEST_MODE:
                post_goal(label, m, None, m["hg"], m["ag"], len(events), m["clock"] or "")
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
    for code, d in targets:
        for ev in get_events(code, d):
            try:
                b = basic_event(ev)
            except Exception as e:
                print("PARSE ERROR", ev.get("id"), e)
                continue
            if not is_top(b, code):
                continue
            mins = (b["dt"] - now).total_seconds() / 60
            if b["state"] == "in" or (b["state"] == "pre" and 0 <= mins <= 30):
                watch.add((code, d))
            if b["state"] == "in":
                try:
                    process_live(LEAGUES[code], ev, state)
                except Exception as e:
                    print("LIVE ERROR", ev.get("id"), e)
    if full:
        state["watch"] = sorted(watch)
        state["scan_ts"] = time.time()
    if not TEST_MODE:
        save_state(state)


if __name__ == "__main__":
    main()
