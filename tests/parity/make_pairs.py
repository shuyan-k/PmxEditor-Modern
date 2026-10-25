import os, glob
from PIL import Image, ImageDraw, ImageFont
OUT = r"tests\parity\pairs"
os.makedirs(OUT, exist_ok=True)
FONT = r"C:\Windows\Fonts\msyh.ttc"
def label(size, h=34):
    return ImageFont.truetype(FONT, 20)
OPS = ["E1","E2","E3","E4","E5","B1","B2","B3","M1","M2","V1","F1","P1","J1","S1","S2","U1","N1","N2",
       "M4","M5","M6","V2","B4","B5","P2","F2","I2"]
H = 760
for op in OPS:
    a = r"tests\parity\shots\%s_orig.png" % op
    b = r"tests\shots\parity_%s_mod.png" % op
    if not (os.path.exists(a) and os.path.exists(b)):
        print("skip", op); continue
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    def fit(im):
        w = int(im.width * H / im.height)
        return im.resize((w, H), Image.LANCZOS)
    ia, ib = fit(ia), fit(ib)
    pad, bar = 12, 34
    W = ia.width + ib.width + pad * 3
    canvas = Image.new("RGB", (W, H + bar + pad), (245, 245, 245))
    canvas.paste(ia, (pad, bar))
    canvas.paste(ib, (pad * 2 + ia.width, bar))
    d = ImageDraw.Draw(canvas)
    f = label(20)
    d.text((pad + 6, 6), "原版 PmxEditor — %s" % op, font=f, fill=(20, 20, 20))
    d.text((pad * 2 + ia.width + 6, 6), "PmxStudio — %s" % op, font=f, fill=(20, 20, 20))
    d.line([(pad + ia.width + pad // 2, 0), (pad + ia.width + pad // 2, H + bar)], fill=(180, 180, 180), width=2)
    canvas.save(os.path.join(OUT, "%s_pair.png" % op))
    print("ok", op, canvas.size)
