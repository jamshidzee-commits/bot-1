"""Bir martalik: tanlangan turnir jadvalini kanalga yuboradi (qo'lda ishga tushiriladi).
Ishlatish: TABLE_CODE=uefa.champions python scripts/post_table_once.py"""
import os
from datetime import datetime

from post_results import TASHKENT, send_photo, TEST_MODE
from standings import fetch_table, make_table_image, caption

code = os.environ.get("TABLE_CODE", "uefa.champions")
now = datetime.now(TASHKENT)
rows = fetch_table(code)
print("rows:", len(rows))
if len(rows) < 8:
    import requests
    from standings import STANDINGS
    j = requests.get(STANDINGS.format(code=code), timeout=30).json()
    print("KEYS", list(j.keys()))
    for c in j.get("children", []):
        print("CHILD", c.get("name"), len(c.get("standings", {}).get("entries", [])))
    for u in ("https://site.api.espn.com/apis/v2/sports/soccer/%s/standings?season=2026&level=3" % code,):
        jj = requests.get(u, timeout=30).json()
        for c in jj.get("children", []):
            print("CHILD2", c.get("name"), len(c.get("standings", {}).get("entries", [])))
    raise SystemExit("jadval topilmadi")
img = make_table_image(code, rows, now, sub_text="LIGA BOSQICHI JADVALI")
if os.environ.get("PREVIEW"):
    img.save("/tmp/table.jpg", quality=90)
    print("saved /tmp/table.jpg", img.size)
elif not TEST_MODE:
    cap = caption(code).replace("Tur yakunlandi — turnir jadvali", "Liga bosqichi — turnir jadvali")
    print("sent:", bool(send_photo(img, cap)))
