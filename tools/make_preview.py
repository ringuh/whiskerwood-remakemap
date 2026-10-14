"""Builds docs/preview.jpg (Workshop preview, must stay under 1 MB) from an in-game screenshot.
Usage: python tools/make_preview.py path/to/screenshot.png"""
import sys, os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SRC = sys.argv[1]
OUT = os.path.join(os.path.dirname(__file__), '..', 'docs', 'preview.jpg')
W, H = 1280, 720
PANEL_X = 820                       # screenshot on the left, text panel on the right
GOLD, CREAM, DIM = (214, 180, 98), (238, 226, 196), (170, 178, 196)
NAVY = (9, 16, 30)

TITLE = '/usr/share/fonts/truetype/crosextra/Caladea-Bold.ttf'
BODY = '/usr/share/fonts/opentype/inter/Inter-SemiBold.otf'
BODYR = '/usr/share/fonts/opentype/inter/Inter-Regular.otf'
f = lambda p, s: ImageFont.truetype(p, s)

shot = Image.open(SRC).convert('RGB')
sw, sh = shot.size
# crop around the island, full height, keep the game's own Remake button (top centre)
cw = int(sh * (PANEL_X + 120) / H)
x0 = max(0, min(sw - cw, 170))
crop = shot.crop((x0, 0, x0 + cw, sh))
scale = H / sh
crop = crop.resize((int(cw * scale), H), Image.LANCZOS)

img = Image.new('RGB', (W, H), NAVY)
img.paste(crop, (0, 0))

# soft fade from the picture into the panel
fade = Image.new('L', (W, H), 0)
fd = ImageDraw.Draw(fade)
for x in range(PANEL_X - 160, W):
    a = min(255, int(255 * ((x - (PANEL_X - 160)) / 200) ** 1.4))
    fd.line([(x, 0), (x, H)], fill=a)
img = Image.composite(Image.new('RGB', (W, H), NAVY), img, fade)

d = ImageDraw.Draw(img)

# highlight the in-game button: glow ring + callout
bx0, by0, bx1, by1 = [int(v) for v in ((655 - x0) * scale, 57 * scale, (806 - x0) * scale, 95 * scale)]
glow = Image.new('L', (W, H), 0)
ImageDraw.Draw(glow).rounded_rectangle((bx0 - 12, by0 - 10, bx1 + 12, by1 + 10), radius=22, outline=255, width=7)
glow = glow.filter(ImageFilter.GaussianBlur(7))
img.paste(Image.new('RGB', (W, H), GOLD), (0, 0), glow)
d = ImageDraw.Draw(img)
d.rounded_rectangle((bx0 - 9, by0 - 7, bx1 + 9, by1 + 7), radius=20, outline=GOLD, width=3)
call = 'click twice on day 1'
cf = f(BODY, 21)
tw = d.textlength(call, font=cf)
cx = (bx0 + bx1) / 2
d.text((cx - tw / 2, by1 + 18), call, font=cf, fill=CREAM, stroke_width=3, stroke_fill=NAVY)

# text panel
x = PANEL_X + 10
d.text((x, 92), 'Remake Map', font=f(TITLE, 68), fill=GOLD)
d.text((x + 2, 178), 'Bad starting spot? Roll a new island.', font=f(BODYR, 22), fill=CREAM)
d.line([(x, 228), (W - 56, 228)], fill=(90, 80, 55), width=2)

items = [('Same new-game settings', 'map size, islands, difficulty, scenario'),
         ('Same starting whiskers', 'the crew you picked comes along'),
         ('New random map', 'a fresh seed every time')]
y = 258
for head, sub in items:
    # diamond bullet
    d.polygon([(x + 9, y + 6), (x + 18, y + 15), (x + 9, y + 24), (x, y + 15)], fill=GOLD)
    d.text((x + 34, y), head, font=f(BODY, 27), fill=CREAM)
    d.text((x + 34, y + 36), sub, font=f(BODYR, 19), fill=DIM)
    y += 92
d.line([(x, y + 6), (W - 56, y + 6)], fill=(90, 80, 55), width=2)
foot = ['The button shows on day 1 of a new colony', 'and disappears when day 2 starts.']
for i, t in enumerate(foot):
    d.text((x, y + 26 + i * 30), t, font=f(BODYR, 20), fill=DIM)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
img.save(OUT, 'JPEG', quality=92, optimize=True)
print(OUT, os.path.getsize(OUT), 'bytes')
