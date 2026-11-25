"""Gol videolari: live gol rasmi chiqqandan keyin rasmiy YouTube kanallarida shu gol klipi paydo bo'lsa,
uni o'sha rasmga javob sifatida yuboradi (video Telegramning o'zida o'ynaydi). Topilmasa — hech narsa o'zgarmaydi."""
import re
import time

CHECK_EVERY_SEC = 300      # YouTube kvotasini tejash: har 5 daqiqada
MAX_AGE_SEC = 30 * 60      # klipni gol rasmidan keyin 30 daqiqagacha qidiramiz, topilmasa — to'xtaymiz
BAD = ("highlight", "full match", "preview", "press conference", "reaction", "interview", "predict", "trailer", "live")


def register(state, ids, code, m, g, hg, ag, minute):
    """Gol rasmi yuborilgach chaqiriladi: klip qidiriladigan ro'yxatga qo'shadi."""
    if not ids or not code:
        return
    state.setdefault("goal_clips", []).append({
        "ids": ids, "code": code, "home": m["home"], "away": m["away"], "hg": hg, "ag": ag,
        "name": (g or {}).get("name", ""), "min": minute or "", "ts": time.time()})
    state["goal_clips"] = state["goal_clips"][-60:]


def _surname(name):
    parts = re.findall(r"[^\W\d_]+", name or "")
    return parts[-1] if parts else ""


def _match(it, item, hk, ak, norm, after_iso):
    title, pub, _ = it["title"], it["pub"], it["vid"]
    t = norm(title)
    if pub < after_iso or any(b in t for b in BAD):
        return False
    both = any(k in t for k in hk) and any(k in t for k in ak)
    one = any(k in t for k in hk) or any(k in t for k in ak)
    sur = norm(_surname(item["name"]))
    score = re.search(rf"\b{item['hg']}\s*[-–:]\s*{item['ag']}\b", t) or re.search(rf"\b{item['ag']}\s*[-–:]\s*{item['hg']}\b", t)
    if sur and len(sur) >= 3 and sur in t and one:
        return True
    return bool(both and "goal" in t and score)


def check(state):
    """Ochiq gollar uchun klip izlaydi; topilsa javob sifatida yuboradi."""
    items = state.get("goal_clips", [])
    now = time.time()
    state["goal_clips"] = items = [i for i in items if not i.get("done") and now - i["ts"] < MAX_AGE_SEC]
    if not items or now - state.get("clip_ts", 0) < CHECK_EVERY_SEC:
        return
    state["clip_ts"] = now
    import highlights as H
    from datetime import datetime, timezone
    used = set(state.setdefault("clip_used", []))
    s = H.load()
    for item in items:
        hk, ak = H.team_keys(item["home"]), H.team_keys(item["away"])
        after_iso = datetime.fromtimestamp(item["ts"] - 120, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for ch_id in H.channels_for(s, item["code"]):
            for title, pub, vid in H.uploads(ch_id):
                if vid in used:
                    continue
                if _match({"title": title, "pub": pub, "vid": vid}, item, hk, ak, H.norm, after_iso):
                    _post(H, item, vid)
                    item["done"] = True
                    used.add(vid)
                    break
            if not item.get("done"):  # diagnostika: kanalning so'nggi sarlavhalari
                state.setdefault("clip_debug", {})[f"{item['home']}|{item['name']}|{item['min']}"] = [
                    f"{pub[5:16]} {title}" for title, pub, _ in H.uploads(ch_id)[:10]]
                for k in list(state["clip_debug"])[:-3]:
                    state["clip_debug"].pop(k)
            if item.get("done"):
                break
    state["clip_used"] = sorted(used)[-300:]


def _post(H, item, vid):
    import html
    url = f"https://www.youtube.com/watch?v={vid}"
    who = f" · {html.escape(item['name'], quote=False)} {html.escape(item['min'], quote=False)}".rstrip() if item["name"] else ""
    text = (f"🎬 <b>Gol videosi</b>{who}\n"
            f"⚽ {html.escape(item['home'], quote=False)} {item['hg']}:{item['ag']} {html.escape(item['away'], quote=False)}\n\n"
            f"{H._channel_footer()}")
    for chat, msg_id in item["ids"].items():
        H.send_news(chat, text, url, reply_parameters={"message_id": msg_id, "allow_sending_without_reply": True})
