#!/usr/bin/env python3
"""fetch_fonts.py — Download MapLibre glyph PBFs for self-hosting.

All labels are normalized to U+00FF by normalize_label(), so only the 0-255
range is strictly needed. Four ranges are downloaded as a safety margin in case
MapLibre prefetches adjacent ranges.

Output: fonts/Noto Sans Regular/{range}.pbf
glyphs in build.py: './fonts/{fontstack}/{range}.pbf'

Run once; PBF files are binary, ~20-80 KB each.
"""
import pathlib
import sys
import urllib.parse
import urllib.request

HERE = pathlib.Path(__file__).parent

FONTS = ["Noto Sans Regular", "Noto Sans Bold"]

# All label text is normalized to Latin-1 (≤ U+00FF) — only 0-255 is required.
# Download 4 ranges so MapLibre never hits a 404 for a prefetch.
RANGES = [f"{i*256}-{i*256+255}" for i in range(4)]  # 0-255 … 768-1023

# Sources tried in order; first valid PBF wins.
# fonts.openmaptiles.org works from Python (no CORS) even if it broke in the browser.
# openmaptiles.github.io/fonts serves the same pre-built set via GitHub Pages.
SOURCES = [
    "https://fonts.openmaptiles.org/{font}/{range}.pbf",
    "https://openmaptiles.github.io/fonts/{font}/{range}.pbf",
    "https://demotiles.maplibre.org/font/{font}/{range}.pbf",
]


def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
        ctype = r.headers.get("Content-Type", "?")
    return data, ctype


def is_valid_pbf(data, ctype):
    """Reject HTML error pages masquerading as PBFs."""
    if "html" in ctype.lower() or "json" in ctype.lower():
        return False
    if len(data) < 10:
        return False
    if data[:5].lower().startswith(b"<!doc") or data[:4].lower() == b"<htm":
        return False
    return True


total_ok = 0
total_want = len(FONTS) * len(RANGES)
for FONT in FONTS:
    print(f"\n=== {FONT} ===")
    font_dir = HERE / "fonts" / FONT
    font_dir.mkdir(parents=True, exist_ok=True)
    font_enc = urllib.parse.quote(FONT)
    for rng in RANGES:
        saved = False
        row_errors = []
        for tmpl in SOURCES:
            url = tmpl.format(font=font_enc, range=rng)
            try:
                data, ctype = fetch_url(url)
                if is_valid_pbf(data, ctype):
                    (font_dir / f"{rng}.pbf").write_bytes(data)
                    print(f"  OK   {rng}.pbf  {len(data):>7} B  [{ctype[:35]}]")
                    total_ok += 1
                    saved = True
                    break
                else:
                    row_errors.append(f"  skip {url[:72]}  ({ctype[:25]}, {len(data)} B)")
            except Exception as e:
                row_errors.append(f"  err  {url[:72]}  {type(e).__name__}: {e}")
        if not saved:
            print(f"  FAIL {rng}.pbf — alle Quellen gescheitert:")
            for line in row_errors:
                print(line)

print(f"\n{total_ok}/{total_want} PBF-Ranges gespeichert -> fonts/")
if total_ok == 0:
    print("FEHLER: Keine PBFs heruntergeladen. Internetverbindung + Quellen pruefen.")
    sys.exit(1)
if total_ok < total_want:
    print("WARNUNG: Nicht alle Ranges verfuegbar (unkritisch wenn 0-255 je Font OK ist).")
print("Naechster Schritt: python build.py")
