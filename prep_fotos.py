#!/usr/bin/env python3
"""Fotos fuer die Chronik aufbereiten (privat_assets, NIE committen).

Liest privat_assets/orig/<id>_<slug>/*.jpg|.jpeg, skaliert auf max. 1600 px lange
Kante (JPEG q~72), STRIPPT saemtliche EXIF-Daten (inkl. GPS!) — die EXIF-Orientierung
wird vorher auf die Pixel angewandt —, schreibt nummeriert (nach Original-Dateiname
sortiert, .JPG/.JPEG gleich behandelt) nach privat_assets/web/<id>_<slug>/NN.jpg und
gibt ein fertiges JSON-Snippet fuer das fotos-Feld auf stdout aus (Captions werden in
touren.json gepflegt).

Aufruf:  python prep_fotos.py <tour_id> [<tour_id> ...]
"""
import json
import pathlib
import sys

from PIL import Image, ImageOps

HERE = pathlib.Path(__file__).parent
ORIG = HERE / "privat_assets" / "orig"
WEB = HERE / "privat_assets" / "web"
MAXEDGE = 1600
QUALITY = 72
TARGET_KB = 330      # Spec-Zielband 150-300 KB; unter der check-Warnung (400 KB) bleiben
MIN_QUALITY = 42     # Qualitaets-Untergrenze fuer grosse Motive
EXTS = {".jpg", ".jpeg"}


def prep_tour(tid):
    dirs = sorted(p for p in ORIG.glob(f"{tid}_*") if p.is_dir())
    if not dirs:
        print(f"# id {tid}: kein Ordner privat_assets/orig/{tid}_*/ gefunden", file=sys.stderr)
        return None
    src_dir = dirs[0]
    slug = src_dir.name                                   # z.B. "16_schladming"
    files = sorted((p for p in src_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in EXTS),
                   key=lambda p: p.name.lower())          # nach Original-Dateiname
    if not files:
        print(f"# id {tid}: keine .jpg/.jpeg in {src_dir}", file=sys.stderr)
        return None
    out_dir = WEB / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    fotos = []
    for n, f in enumerate(files, 1):
        img = Image.open(f)
        img = ImageOps.exif_transpose(img)                # Orientierung anwenden, dann EXIF weg
        img = img.convert("RGB")
        img.thumbnail((MAXEDGE, MAXEDGE), Image.LANCZOS)
        out = out_dir / f"{n:02d}.jpg"
        # Adaptive Qualitaet: q senken, bis unter Zielgroesse (ohne exif= -> EXIF/GPS gestrippt).
        q = QUALITY
        img.save(out, "JPEG", quality=q, optimize=True)
        while out.stat().st_size / 1024 > TARGET_KB and q > MIN_QUALITY:
            q = max(MIN_QUALITY, q - 7)
            img.save(out, "JPEG", quality=q, optimize=True)
        kb = out.stat().st_size / 1024
        rel = f"privat_assets/web/{slug}/{n:02d}.jpg"
        fotos.append({"src": rel, "caption": ""})
        flag = "  !!>400KB" if kb > 400 else ""
        print(f"# {f.name} -> {rel}  ({kb:.0f} KB q{q}, {img.size[0]}x{img.size[1]}){flag}", file=sys.stderr)
    return int(tid), fotos


if __name__ == "__main__":
    ids = sys.argv[1:]
    if not ids:
        print("Aufruf: python prep_fotos.py <tour_id> [<tour_id> ...]", file=sys.stderr)
        sys.exit(1)
    snippet = {}
    for tid in ids:
        r = prep_tour(tid)
        if r:
            snippet[r[0]] = r[1]
    # JSON-Snippet fuers fotos-Feld (Captions in touren.json nachtragen/pflegen):
    print(json.dumps(snippet, ensure_ascii=False, indent=1))
