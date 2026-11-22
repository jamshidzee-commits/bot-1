"""Gol uchun qisqa animatsion GIF (o'zimizning kartochkadan): zoom, chaqnash, "GOOOOL!" yozuvi.
Faqat o'z grafikamiz — begona efir/video ishlatilmaydi. ffmpeg kerak (GitHub Actions'da bor)."""
import os
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw

from post_results import F

WIDTH = 540
FPS = 12
SECONDS = 4


def _ease_out_back(x):
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def make_goal_video(card, text="GOOOOL!", color=(255, 205, 70)):
    """card: PIL rasm (kartochka). Qaytaradi: gif baytlari yoki None (ffmpeg yo'q/xato)."""
    if not shutil.which("ffmpeg"):
        print("VIDEO: ffmpeg topilmadi")
        return None
    w = WIDTH
    h = int(card.height * w / card.width) // 2 * 2
    base = card.convert("RGB").resize((w, h), Image.LANCZOS)
    n = FPS * SECONDS
    tmp = tempfile.mkdtemp(prefix="goalvid")
    try:
        for i in range(n):
            t = i / FPS
            z = 1.0 + 0.05 * (i / (n - 1))  # sekin yaqinlashish
            cw, ch = w / z, h / z
            x0, y0 = (w - cw) / 2, (h - ch) / 2
            fr = base.resize((w, h), Image.BICUBIC, box=(x0, y0, x0 + cw, y0 + ch)).convert("RGBA")
            ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            # "GOOOOL!" yozuvi: 0..0.6s sakrab chiqadi, 2.4s gacha turadi, 3.2s gacha so'nadi
            if t < 3.2:
                p = min(t / 0.6, 1.0)
                s = max(0.05, _ease_out_back(p))
                a = 255 if t < 2.4 else int(255 * (1 - (t - 2.4) / 0.8))
                size = max(10, int(118 * s * w / 1080 * 1.5))
                font = F(size, True)
                cy = int(h * 0.5)
                bw = d.textlength(text, font=font)
                d.rounded_rectangle((w / 2 - bw / 2 - 40, cy - size * 0.75, w / 2 + bw / 2 + 40, cy + size * 0.75),
                                    24, fill=(0, 0, 0, int(a * 0.62)))
                d.text((w / 2 + 3, cy + 4), text, font=font, fill=(0, 0, 0, a), anchor="mm")
                d.text((w / 2, cy), text, font=font, fill=color + (a,), anchor="mm")
            # chaqnash
            if t < 0.35:
                d.rectangle((0, 0, w, h), fill=(255, 255, 255, int(150 * (1 - t / 0.35))))
            fr.alpha_composite(ov)
            fr.convert("RGB").save(os.path.join(tmp, f"f{i:04d}.jpg"), quality=90)
        out = os.path.join(tmp, "out.gif")
        vf = "split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(tmp, "f%04d.jpg"),
               "-vf", vf, "-loop", "0", out]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            print("VIDEO ffmpeg xato:", r.stderr[-300:])
            return None
        with open(out, "rb") as f:
            return f.read()
    except Exception as e:
        print("VIDEO xato:", e)
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
