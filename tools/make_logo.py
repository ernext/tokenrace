"""Genera il logo di TokenRace: la mascotte (un gettone che corre), l'icona e la favicon.

Uso (dalla cartella del progetto):
    python tools/make_logo.py            # rigenera gli SVG in assets/logo/
    python tools/make_logo.py --png      # anche i PNG e docs/social-preview.png (serve Google Chrome)

Per cambiare colori o forme modifica le costanti e i pezzi qui sotto, poi rilancia lo script.
Gli SVG generati sono i file sorgente usati da README e app: non modificarli a mano.
"""
import os
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "logo"
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

K = "#2A1A12"        # contorno
OR = "#FF5A1F"       # arancione TokenRace
EDGE = "#B93A0C"     # spessore del gettone

DEFS = f"""
<defs>
  <filter id="sticker" x="-15%" y="-15%" width="130%" height="130%">
    <feMorphology in="SourceAlpha" operator="dilate" radius="6" result="d"/>
    <feFlood flood-color="#FFFFFF"/><feComposite in2="d" operator="in" result="w"/>
    <feMerge><feMergeNode in="w"/><feMergeNode in="SourceGraphic"/></feMerge>
  </filter>
  <clipPath id="edge"><circle cx="153" cy="133" r="80"/></clipPath>
  <pattern id="chk" width="12" height="12" patternUnits="userSpaceOnUse">
    <rect width="12" height="12" fill="#FFFFFF"/>
    <rect width="6" height="6" fill="#1E1E1E"/><rect x="6" y="6" width="6" height="6" fill="#1E1E1E"/>
  </pattern>
  <radialGradient id="face" cx="0.38" cy="0.32" r="0.8">
    <stop offset="0" stop-color="#FF8A4F"/><stop offset="0.55" stop-color="{OR}"/><stop offset="1" stop-color="#E5470F"/>
  </radialGradient>
  <clipPath id="coin"><circle cx="140" cy="128" r="80"/></clipPath>
  <clipPath id="mouth"><path d="M114 150 Q141 186 170 147 Z"/></clipPath>
</defs>"""

SPEED = f"""
<g stroke-linecap="round" fill="none">
  <path d="M4 150 H34" stroke="{OR}" stroke-width="9"/>
  <path d="M14 174 H52" stroke="{K}" stroke-width="9"/>
  <path d="M8 198 H58" stroke="#FFA27A" stroke-width="9"/>
</g>"""

TAILS = f"""
<g stroke="{K}" stroke-width="5" stroke-linejoin="round">
  <path d="M70 86 C50 76 34 84 14 72 L20 94 C38 100 52 96 70 102 Z" fill="url(#chk)"/>
  <path d="M70 100 C54 108 40 118 22 116 L32 132 C48 130 58 120 72 112 Z" fill="url(#chk)"/>
</g>"""

def shoe(x, y, rot):
    return (f'<g transform="translate({x} {y}) rotate({rot})" stroke="{K}" stroke-width="5" stroke-linejoin="round">'
            f'<path d="M-17 7 Q-17 -10 0 -10 Q21 -8 23 5 Q21 11 -17 7 Z" fill="#FFFFFF"/>'
            f'<path d="M-12 3 H18" stroke="{OR}" stroke-width="4"/></g>')

BACK_LIMBS = f"""
<g stroke="{K}" stroke-linecap="round" stroke-linejoin="round" fill="none" stroke-width="9">
  <path d="M74 150 Q54 158 46 142"/>
  <path d="M118 200 Q104 214 86 204"/>
</g>
<circle cx="45" cy="135" r="11" fill="#FFFFFF" stroke="{K}" stroke-width="5"/>
""" + shoe(78, 196, 35)

FRONT_LEG = f"""
<path d="M160 204 Q172 218 174 234" stroke="{K}" stroke-width="9" stroke-linecap="round" fill="none"/>
""" + shoe(180, 238, 0)

FRONT_ARM = f"""
<path d="M214 148 Q240 152 242 126" stroke="{K}" stroke-width="9" stroke-linecap="round" fill="none"/>
<circle cx="242" cy="119" r="11" fill="#FFFFFF" stroke="{K}" stroke-width="5"/>"""

REEDS = """<path d="M164.8 66.0 L167.6 50.3"/><path d="M174.0 68.3 L179.0 53.1"/><path d="M182.8 71.9 L189.8 57.5"/><path d="M191.0 76.6 L200.0 63.4"/><path d="M198.5 82.5 L209.2 70.6"/><path d="M205.1 89.3 L217.3 79.0"/><path d="M210.7 97.0 L224.2 88.5"/><path d="M215.1 105.3 L229.7 98.8"/><path d="M218.4 114.3 L233.7 109.8"/><path d="M220.3 123.5 L236.2 121.3"/><path d="M221.0 133.0 L237.0 133.0"/><path d="M220.3 142.5 L236.2 144.7"/><path d="M218.4 151.7 L233.7 156.2"/><path d="M215.1 160.7 L229.7 167.2"/><path d="M210.7 169.0 L224.2 177.5"/><path d="M205.1 176.7 L217.3 187.0"/><path d="M198.5 183.5 L209.2 195.4"/><path d="M191.0 189.4 L200.0 202.6"/><path d="M182.8 194.1 L189.8 208.5"/><path d="M174.0 197.7 L179.0 212.9"/><path d="M164.8 200.0 L167.6 215.7"/><path d="M155.4 201.0 L155.9 216.9"/><path d="M145.9 200.6 L144.2 216.5"/><path d="M136.5 199.0 L132.7 214.5"/><path d="M127.5 196.0 L121.5 210.9"/><path d="M119.0 191.9 L111.0 205.7"/><path d="M111.1 186.6 L101.3 199.2"/><path d="M104.1 180.2 L92.6 191.4"/><path d="M98.0 173.0 L85.0 182.4"/><path d="M93.0 164.9 L78.8 172.4"/><path d="M89.1 156.3 L74.1 161.7"/><path d="M86.5 147.1 L70.8 150.5"/><path d="M85.2 137.7 L69.2 138.9"/><path d="M85.2 128.3 L69.2 127.1"/>"""

def coin(band=True, crown=False):
    s = ""
    if crown:
        s += f"""<g stroke="{K}" stroke-width="5" stroke-linejoin="round">
  <rect x="128" y="30" width="24" height="16" rx="4" fill="{EDGE}"/>
  <rect x="120" y="22" width="40" height="12" rx="5" fill="{OR}"/>
  <rect x="196" y="46" width="18" height="12" rx="4" fill="{EDGE}" transform="rotate(45 205 52)"/>
</g>"""
    s += f"""
<circle cx="153" cy="133" r="80" fill="{EDGE}" stroke="{K}" stroke-width="7"/>
<g clip-path="url(#edge)" stroke="{K}" stroke-width="3.5" stroke-opacity="0.8">{REEDS}</g>
<circle cx="140" cy="128" r="80" fill="url(#face)"/>
<circle cx="140" cy="128" r="68" fill="none" stroke="#FFFFFF" stroke-opacity="0.28" stroke-width="4"/>
<path d="M82 118 A60 60 0 0 1 100 84" fill="none" stroke="#FFFFFF" stroke-opacity="0.55" stroke-width="7" stroke-linecap="round"/>"""
    if band:
        s += f"""<g clip-path="url(#coin)">
  <path d="M50 86 Q140 60 230 86 L230 106 Q140 80 50 106 Z" fill="url(#chk)" stroke="{K}" stroke-width="5"/>
</g>"""
    s += f"""<circle cx="140" cy="128" r="80" fill="none" stroke="{K}" stroke-width="7"/>"""
    # faccia
    s += f"""
<g stroke="{K}" stroke-linecap="round">
  <path d="M106 106 Q117 100 129 106" stroke-width="7" fill="none"/><path d="M153 106 Q165 100 177 106" stroke-width="7" fill="none"/>
</g>
<g stroke="{K}" stroke-width="5">
  <ellipse cx="118" cy="128" rx="13" ry="17" fill="#FFFFFF"/>
  <ellipse cx="164" cy="128" rx="13" ry="17" fill="#FFFFFF"/>
</g>
<circle cx="123" cy="131" r="7.5" fill="{K}"/><circle cx="169" cy="131" r="7.5" fill="{K}"/>
<circle cx="126" cy="127" r="2.6" fill="#FFFFFF"/><circle cx="172" cy="127" r="2.6" fill="#FFFFFF"/>
<ellipse cx="98" cy="154" rx="9" ry="6" fill="#FFB4A0" opacity="0.75"/>
<ellipse cx="186" cy="152" rx="9" ry="6" fill="#FFB4A0" opacity="0.75"/>
<path d="M114 150 Q141 186 170 147 Z" fill="{K}" stroke="{K}" stroke-width="5" stroke-linejoin="round"/>
<g clip-path="url(#mouth)"><ellipse cx="145" cy="172" rx="14" ry="8" fill="#FF8FA3"/></g>"""
    return s

FLAG = f"""
<g stroke="{K}" stroke-linejoin="round" stroke-linecap="round">
  <path d="M232 132 L250 22" stroke-width="6" fill="none"/>
  <path d="M250 24 Q264 18 276 24 Q288 30 300 24 L294 66 Q282 72 270 66 Q258 60 244 66 Z" fill="url(#chk)" stroke-width="5"/>
</g>"""

def svg(body, vb="-8 -4 272 264", lean=6):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}">{DEFS}'
            f'<g filter="url(#sticker)"><g transform="rotate({lean} 140 140)">{body}</g></g></svg>')


ICON_SMALL = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<defs><pattern id="c2" width="10" height="10" patternUnits="userSpaceOnUse">
<rect width="10" height="10" fill="#FFFFFF"/><rect width="5" height="5" fill="#1E1E1E"/><rect x="5" y="5" width="5" height="5" fill="#1E1E1E"/></pattern>
<clipPath id="cc"><circle cx="31" cy="33" r="27"/></clipPath></defs>
<circle cx="33" cy="33.5" r="30.5" fill="#FFFFFF"/>
<circle cx="34" cy="34" r="27" fill="{EDGE}" stroke="{K}" stroke-width="4"/>
<circle cx="31" cy="33" r="27" fill="{OR}"/>
<g clip-path="url(#cc)"><path d="M0 16 Q31 6 64 16 L64 26 Q31 16 0 26 Z" fill="url(#c2)" stroke="{K}" stroke-width="3"/></g>
<circle cx="31" cy="33" r="27" fill="none" stroke="{K}" stroke-width="4"/>
<ellipse cx="24" cy="35" rx="5" ry="6.5" fill="#FFFFFF" stroke="{K}" stroke-width="2.5"/>
<ellipse cx="39" cy="35" rx="5" ry="6.5" fill="#FFFFFF" stroke="{K}" stroke-width="2.5"/>
<circle cx="26" cy="36" r="3" fill="{K}"/><circle cx="41" cy="36" r="3" fill="{K}"/>
<path d="M22 46 Q31 55 41 45 Z" fill="{K}" stroke="{K}" stroke-width="2.5" stroke-linejoin="round"/>
</svg>"""

files = {
    "tokenrace-mascot.svg": svg(SPEED + TAILS + BACK_LIMBS + FRONT_LEG + coin() + FRONT_ARM),
    "tokenrace-icon.svg": svg(SPEED + TAILS + coin(), vb="-6 28 250 206", lean=4),
    "tokenrace-favicon.svg": ICON_SMALL,
}

SOCIAL_HTML = """<!doctype html><meta charset="utf-8"><style>
body{margin:0;width:1280px;height:640px;background:linear-gradient(135deg,#FFF6F1 0%,#FFFFFF 60%);font-family:-apple-system,"SF Pro Display",system-ui,sans-serif;display:flex;align-items:center;overflow:hidden;position:relative}
.chk{position:absolute;left:0;right:0;bottom:0;height:28px;background:repeating-conic-gradient(#1E1E1E 0 25%,#fff 0 50%) 0 0/28px 28px}
img{height:440px;margin-left:60px}
.t{margin-left:40px}
h1{font-size:118px;margin:0;letter-spacing:-3px;font-weight:800;color:#2A1A12}
h1 span{color:#FF5A1F}
p{font-size:40px;margin:6px 0 0;color:#5a4a42;font-weight:600}
.m{margin-top:34px;display:inline-block;background:#FF5A1F;color:#fff;font-size:32px;font-weight:700;padding:12px 26px;border-radius:999px}
</style><img src="{mascot}"><div class="t"><h1>Token<span>Race</span></h1>
<p>LLM inference speed test</p><p style="font-size:27px;font-weight:500;white-space:nowrap">Ollama · LM Studio · oMLX · Rapid-MLX · llama.cpp · vLLM · …</p>
<div class="m">Measure first, then choose.</div></div><div class="chk"></div>
"""


def chrome_png(html: str, out: pathlib.Path, w: int, h: int, transparent: bool) -> None:
    """Disegna una pagina HTML con Chrome headless e la salva come PNG."""
    with tempfile.TemporaryDirectory() as tmp:
        page = pathlib.Path(tmp) / "page.html"
        page.write_text(html, encoding="utf-8")
        args = [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                "--force-device-scale-factor=1", f"--user-data-dir={tmp}/profile",
                f"--window-size={w},{h}", f"--screenshot={out}", page.as_uri()]
        if transparent:
            args.insert(2, "--default-background-color=00000000")
        subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (OUT / name).write_text(content, encoding="utf-8")
        print("scritto", (OUT / name).relative_to(ROOT))
    if "--png" not in sys.argv:
        return
    for name, px in (("tokenrace-mascot", 512), ("tokenrace-icon", 512), ("tokenrace-favicon", 128)):
        src = (OUT / f"{name}.svg").as_uri()
        html = (f"<!doctype html><style>html,body{{margin:0;background:transparent}}"
                f"img{{width:{px}px;height:{px}px;object-fit:contain;display:block}}</style><img src='{src}'>")
        chrome_png(html, OUT / f"{name}.png", px, px, transparent=True)
        print("scritto", (OUT / f"{name}.png").relative_to(ROOT))
    social = ROOT / "docs" / "social-preview.png"
    chrome_png(SOCIAL_HTML.replace("{mascot}", (OUT / "tokenrace-mascot.svg").as_uri()), social, 1280, 640, False)
    print("scritto", social.relative_to(ROOT))


if __name__ == "__main__":
    main()
